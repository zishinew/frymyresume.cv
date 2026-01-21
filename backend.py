from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import PyPDF2
import io
import os
import re
import time
import base64
import requests
import asyncio
import json
from datetime import date, datetime
from google import genai
from dotenv import load_dotenv
from typing import Optional, Any
from app.config import FRONTEND_URL

load_dotenv()

# Import auth modules
from app.routers import auth_router, users_router, jobs_router, friends_router
from app.dependencies import get_current_user_optional, SupabaseUser
from app.supabase_client import get_supabase_admin

app = FastAPI(title="FryMyResume API")

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Include auth routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(jobs_router)
app.include_router(friends_router)

def _strip_trailing_slash(value: str) -> str:
    return value[:-1] if value.endswith("/") else value


allowed_origins = [
    _strip_trailing_slash(FRONTEND_URL),
    "https://frymyresume.cv",
    "https://www.frymyresume.cv",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add WebSocket origins explicitly
ALLOWED_WS_ORIGINS = ["*"]  # Allow all for now

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

# Session storage for behavioral interviews
interview_sessions = {}

# In-memory storage for AI-generated technical problems (prompt + tests)
_generated_technical_sessions: dict[str, dict] = {}
_generated_technical_session_index: dict[str, str] = {}


def _prune_generated_technical_sessions(max_age_seconds: int = 6 * 60 * 60, max_sessions: int = 250) -> None:
    """Best-effort pruning to keep memory bounded."""
    now = time.time()
    # Drop old sessions
    old_ids = [
        sid
        for sid, sess in _generated_technical_sessions.items()
        if (now - float(sess.get("created_at", now))) > max_age_seconds
    ]
    for sid in old_ids:
        _generated_technical_sessions.pop(sid, None)

    # Drop index entries that point to missing sessions
    for key, sid in list(_generated_technical_session_index.items()):
        if sid not in _generated_technical_sessions:
            _generated_technical_session_index.pop(key, None)

    # If still too many, drop oldest
    if len(_generated_technical_sessions) > max_sessions:
        ordered = sorted(
            _generated_technical_sessions.items(),
            key=lambda kv: float(kv[1].get("created_at", 0.0)),
        )
        for sid, _sess in ordered[: max(0, len(ordered) - max_sessions)]:
            _generated_technical_sessions.pop(sid, None)
        for key, sid in list(_generated_technical_session_index.items()):
            if sid not in _generated_technical_sessions:
                _generated_technical_session_index.pop(key, None)


def _extract_first_json_object(text: str) -> dict:
    """Extract the first JSON object from a model response."""
    if not isinstance(text, str):
        raise ValueError("Model response was not text")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("No JSON object found in model response")
    candidate = text[start : end + 1]
    return json.loads(candidate)


def _validate_generated_problem_payload(payload: dict) -> dict:
    """Normalize and validate generated-problem payload."""
    if not isinstance(payload, dict):
        raise ValueError("Generated problem payload must be an object")

    required_keys = ["problem_title", "prompt", "constraints", "examples", "sample_tests", "hidden_tests"]
    for k in required_keys:
        if k not in payload:
            raise ValueError(f"Generated problem missing field: {k}")

    def ensure_tests(value: Any, name: str) -> list[dict]:
        if not isinstance(value, list):
            raise ValueError(f"{name} must be a list")
        normalized: list[dict] = []
        for t in value:
            if not isinstance(t, dict):
                continue
            inp = t.get("input")
            if not isinstance(inp, dict):
                continue
            if "expectedOutput" not in t:
                continue
            normalized.append({"input": inp, "expectedOutput": t.get("expectedOutput")})
        if not normalized:
            raise ValueError(f"{name} had no valid test cases")
        # Ensure serializable
        json.dumps(normalized)
        return normalized

    constraints = payload.get("constraints")
    if not isinstance(constraints, list):
        constraints = [str(constraints)] if constraints is not None else []

    examples = payload.get("examples")
    if not isinstance(examples, list):
        examples = []
    else:
        cleaned_examples = []
        for ex in examples:
            if not isinstance(ex, dict):
                continue
            inp = ex.get("input")
            out = ex.get("output")
            if not isinstance(inp, dict):
                continue
            cleaned_examples.append(
                {
                    "input": inp,
                    "output": out,
                    "explanation": str(ex.get("explanation") or "").strip(),
                }
            )
        examples = cleaned_examples

    sample_tests = ensure_tests(payload.get("sample_tests"), "sample_tests")
    hidden_tests = ensure_tests(payload.get("hidden_tests"), "hidden_tests")

    # Enforce stable test counts for UI/UX and grading consistency
    if len(sample_tests) < 3 or len(hidden_tests) < 10:
        raise ValueError("Generated tests did not meet minimum counts (need 3 sample + 10 hidden).")
    sample_tests = sample_tests[:3]
    hidden_tests = hidden_tests[:10]

    # Starter code (optional in model output; we will provide defaults)
    starter_code_raw = payload.get("starter_code")
    starter_code: dict[str, str] = {}
    if isinstance(starter_code_raw, dict):
        for k, v in starter_code_raw.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                starter_code[k.strip().lower()] = v

    # Infer a minimal shape from sample input keys (for nicer templates)
    input_keys: list[str] = []
    try:
        first_inp = sample_tests[0].get("input") if sample_tests else None
        if isinstance(first_inp, dict):
            input_keys = list(first_inp.keys())[:8]
    except Exception:
        input_keys = []

    if "python" not in starter_code:
        keys_hint = ", ".join([f"'{k}'" for k in input_keys]) if input_keys else "(see prompt)"
        starter_code["python"] = (
            "class Solution:\n"
            "    def solution(self, input):\n"
            f"        \"\"\"input is a dict/object with keys: {keys_hint}\"\"\"\n"
            "        # TODO: implement\n"
            "        pass\n"
        )
    if "javascript" not in starter_code:
        keys_hint = ", ".join([k for k in input_keys]) if input_keys else "/* see prompt */"
        starter_code["javascript"] = (
            "function solution(input) {\n"
            f"  // input is an object with keys: {keys_hint}\n"
            "  // TODO: implement\n"
            "}\n"
        )

    prompt_text = str(payload.get("prompt") or "").strip()
    if len(prompt_text) > 4000:
        prompt_text = prompt_text[:4000].rstrip() + "…"

    normalized_payload = {
        "problem_title": str(payload.get("problem_title") or "Technical Problem").strip() or "Technical Problem",
        "prompt": prompt_text,
        "constraints": [str(c).strip() for c in constraints if str(c).strip()],
        "examples": examples,
        "sample_tests": sample_tests,
        "hidden_tests": hidden_tests,
        "starter_code": starter_code,
        "input_notes": str(payload.get("input_notes") or "").strip(),
        "output_notes": str(payload.get("output_notes") or "").strip(),
    }
    if not normalized_payload["prompt"]:
        raise ValueError("Generated problem prompt was empty")

    return normalized_payload


def _generate_problem_fallback(question: dict) -> dict:
    title = str(question.get("title") or "Technical Problem").strip()
    return {
        "problem_title": f"Practice: {title}",
        "prompt": (
            "Write a function `solution(input)` that returns the sum of the integers in `input.nums`.\n\n"
            "Input is a JSON object. Example: `{\"nums\": [1, 2, 3]}`."
        ),
        "constraints": ["1 ≤ len(nums) ≤ 10^5", "Each number fits in 32-bit signed integer"],
        "examples": [
            {"input": {"nums": [1, 2, 3]}, "output": 6, "explanation": "1+2+3 = 6"},
        ],
        "sample_tests": [
            {"input": {"nums": [1, 2, 3]}, "expectedOutput": 6},
            {"input": {"nums": [10]}, "expectedOutput": 10},
            {"input": {"nums": [-1, 1]}, "expectedOutput": 0},
        ],
        "hidden_tests": [
            {"input": {"nums": [0, 0, 0]}, "expectedOutput": 0},
            {"input": {"nums": [-5, 2, 7]}, "expectedOutput": 4},
            {"input": {"nums": [100, 200, 300]}, "expectedOutput": 600},
            {"input": {"nums": [1, -1, 1, -1]}, "expectedOutput": 0},
            {"input": {"nums": [42]}, "expectedOutput": 42},
            {"input": {"nums": [2, 2, 2, 2]}, "expectedOutput": 8},
            {"input": {"nums": [-10, -20]}, "expectedOutput": -30},
            {"input": {"nums": [3, 1, 4, 1, 5]}, "expectedOutput": 14},
            {"input": {"nums": [7, 0, -7]}, "expectedOutput": 0},
            {"input": {"nums": [999999]}, "expectedOutput": 999999},
        ],
        "input_notes": "`input` will be a dict/object.",
        "output_notes": "Return a JSON-serializable value (number, string, array, object).",
    }


async def _generate_original_problem_from_metadata(question: dict) -> dict:
    """Use Gemini to generate an original problem prompt + deterministic tests.

    Important: We do not fetch or reproduce any copyrighted LeetCode statements.
    """
    title = str(question.get("title") or "").strip()
    difficulty = str(question.get("difficulty") or "medium").strip()
    topics = question.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    topics_str = ", ".join([str(t) for t in topics[:8]])

    prompt = f"""You are creating an ORIGINAL coding interview problem for practice.

Do NOT copy or paraphrase any existing LeetCode problem statement. Do NOT mention LeetCode. The output must be novel.

Use only this metadata as inspiration (title/topics), but create a distinct problem:
- Title (inspiration only): {title}
- Difficulty target: {difficulty}
- Topics (inspiration only): {topics_str}

The candidate will implement `solution(input)` where `input` is a JSON object/dict.
Return ONLY valid JSON (no markdown) with this schema:
{{
  "problem_title": string,
  "prompt": string,
  "constraints": string[],
  "input_notes": string,
  "output_notes": string,
    "starter_code": {"python": string, "javascript": string},
  "examples": [{{"input": object, "output": any, "explanation": string}}],
  "sample_tests": [{{"input": object, "expectedOutput": any}}],
  "hidden_tests": [{{"input": object, "expectedOutput": any}}]
}}

Requirements:
- Keep the prompt concise but clear (<= 250 words).
- Provide 2-3 examples.
- Provide exactly 3 sample_tests and 10 hidden_tests.
- Ensure tests are consistent with the prompt and fully deterministic.
- expectedOutput must be JSON-serializable.
"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = await call_gemini_with_retry_async(
        client=client,
        model="gemini-2.5-flash",
        contents=prompt,
        max_retries=3,
        initial_delay=2,
    )

    payload = _extract_first_json_object(response.text or "")
    return _validate_generated_problem_payload(payload)

# Cache for SimplifyJobs internship listings (parsed from README.md)
_simplifyjobs_cache = {
    "fetched_at": 0.0,
    "etag": None,
    "jobs": [],
    "source": "https://github.com/SimplifyJobs/Summer2026-Internships",
    # NOTE: This repo's active branch is typically `dev` (not `main`).
    "readme_raw_url": "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
}


def _strip_markdown(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    # Convert markdown links [name](url) -> name
    t = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", r"\1", t)
    # Drop leftover markdown/image html noise
    t = re.sub(r"<img[^>]*>", "", t, flags=re.IGNORECASE)
    t = re.sub(r"</?a[^>]*>", "", t, flags=re.IGNORECASE)
    t = re.sub(r"</?details[^>]*>", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"</?summary[^>]*>", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"</?br\s*/?>", ", ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_first_url(markdown_or_html: str) -> Optional[str]:
    if not isinstance(markdown_or_html, str):
        return None
    # href="..."
    m = re.search(r"href=\"([^\"]+)\"", markdown_or_html)
    if m:
        return m.group(1)
    # markdown [..](url)
    m = re.search(r"\[[^\]]*\]\((https?://[^\)]+)\)", markdown_or_html)
    if m:
        return m.group(1)
    # bare url
    m = re.search(r"(https?://\S+)", markdown_or_html)
    if m:
        return m.group(1).rstrip(')')
    return None


def _parse_simplifyjobs_readme_tables(readme: str) -> list[dict]:
    jobs: list[dict] = []
    current_section = ""
    lines = readme.splitlines()

    def parse_html_table(table_html: str, category: str) -> list[dict]:
        parsed: list[dict] = []
        last_company_name: Optional[str] = None
        last_company_url: Optional[str] = None
        last_company_raw: Optional[str] = None

        # Extract each <tr>...</tr> block
        for row_html in re.findall(r"<tr>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL):
            # Skip header rows
            if re.search(r"<th\b", row_html, flags=re.IGNORECASE):
                continue

            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row_html, flags=re.IGNORECASE | re.DOTALL)
            if len(cells) < 4:
                continue

            company_cell, role_cell, location_cell, app_cell = cells[0], cells[1], cells[2], cells[3]
            age_cell = cells[4] if len(cells) >= 5 else ""

            company_url = _extract_first_url(company_cell)
            company_name = _html_to_text(company_cell)
            company_name = re.sub(r"[🔥🎓🛂🇺🇸]", "", company_name).strip()

            # Rows for the same company often use a "↳" cell.
            if company_name in {"↳", ""} and last_company_name:
                company_name = last_company_name
                company_url = company_url or last_company_url
                company_raw = last_company_raw or company_cell
            else:
                company_raw = company_cell
                last_company_name = company_name or last_company_name
                last_company_url = company_url or last_company_url
                last_company_raw = company_raw

            role_title = _html_to_text(role_cell)
            location = _html_to_text(location_cell)
            location = location.replace("</br>", ", ").replace("<br>", ", ")
            location = re.sub(r"\s*,\s*", ", ", location)
            location = re.sub(r"\s+", " ", location).strip(" ,")
            apply_url = _extract_first_url(app_cell)

            parsed.append({
                "source": "simplifyjobs_summer2026",
                "category": category or "",
                "company": company_name,
                "company_url": company_url,
                "role": role_title,
                "location": location,
                "apply_url": apply_url,
                "age": _html_to_text(age_cell),
                # Provide all description fields we have from the repo row
                "raw": {
                    "company_cell": company_raw,
                    "role_cell": role_cell,
                    "location_cell": location_cell,
                    "application_cell": app_cell,
                    "age_cell": age_cell,
                    "row": "<tr>" + row_html.strip() + "</tr>",
                },
            })

        return parsed

    def normalize_company(company_cell: str) -> tuple[str, Optional[str], str]:
        raw = company_cell
        url = _extract_first_url(company_cell)
        name = _strip_markdown(company_cell)
        # Remove common legend emoji that are not part of the company name
        name = re.sub(r"[🔥🎓🛂🇺🇸]", "", name).strip()
        return name, url, raw

    def normalize_location(location_cell: str) -> str:
        t = _strip_markdown(location_cell)
        t = t.replace("</br>", ", ").replace("<br>", ", ")
        t = re.sub(r"\s*,\s*", ", ", t)
        t = re.sub(r"\s+", " ", t).strip(" ,")
        return t

    in_table = False
    in_html_table = False
    html_table_buf: list[str] = []
    for line in lines:
        # Track sections so we can include category context
        if line.startswith("## "):
            current_section = line.replace("##", "").strip()

        # HTML tables are used in the current SimplifyJobs README.
        if "<table" in line.lower():
            in_html_table = True
            html_table_buf = [line]
            continue

        if in_html_table:
            html_table_buf.append(line)
            if "</table>" in line.lower():
                table_html = "\n".join(html_table_buf)
                jobs.extend(parse_html_table(table_html, current_section))
                in_html_table = False
                html_table_buf = []
            continue

        # Detect table header
        if re.match(r"^\|\s*Company\s*\|\s*Role\s*\|\s*Location\s*\|", line):
            in_table = True
            continue
        # Separator row
        if in_table and re.match(r"^\|\s*-+\s*\|", line):
            continue

        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue

            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if len(parts) < 4:
                continue
            company_cell, role_cell, location_cell, app_cell = parts[0], parts[1], parts[2], parts[3]
            age_cell = parts[4] if len(parts) >= 5 else ""

            company_name, company_url, company_raw = normalize_company(company_cell)
            role_title = _strip_markdown(role_cell)
            location = normalize_location(location_cell)
            apply_url = _extract_first_url(app_cell)

            jobs.append({
                "source": "simplifyjobs_summer2026",
                "category": current_section or "",
                "company": company_name,
                "company_url": company_url,
                "role": role_title,
                "location": location,
                "apply_url": apply_url,
                "age": _strip_markdown(age_cell),
                # Provide all description fields we have from the repo row
                "raw": {
                    "company_cell": company_raw,
                    "role_cell": role_cell,
                    "location_cell": location_cell,
                    "application_cell": app_cell,
                    "age_cell": age_cell,
                    "row": line.strip(),
                },
            })

    # Deduplicate by (company, role, location, apply_url)
    seen = set()
    deduped: list[dict] = []
    for j in jobs:
        key = (j.get("company"), j.get("role"), j.get("location"), j.get("apply_url"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(j)
    return deduped


def _get_simplifyjobs_listings_cached_sync(max_age_seconds: int = 60 * 60) -> list[dict]:
    """Synchronous version - use _get_simplifyjobs_listings_cached for async contexts."""
    now = time.time()
    if _simplifyjobs_cache["jobs"] and (now - float(_simplifyjobs_cache["fetched_at"])) < max_age_seconds:
        return _simplifyjobs_cache["jobs"]

    # Repo sometimes changes default branch; try a few known candidates.
    candidates = [
        _simplifyjobs_cache.get("readme_raw_url") or "",
        "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
        "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/main/README.md",
        "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/master/README.md",
    ]
    seen_urls: set[str] = set()
    urls: list[str] = []
    for u in candidates:
        u = (u or "").strip()
        if not u or u in seen_urls:
            continue
        seen_urls.add(u)
        urls.append(u)

    last_error: Optional[Exception] = None
    for url in urls:
        headers = {}
        # Only send If-None-Match for the current configured URL.
        if url == _simplifyjobs_cache.get("readme_raw_url") and _simplifyjobs_cache.get("etag"):
            headers["If-None-Match"] = _simplifyjobs_cache["etag"]

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 304 and _simplifyjobs_cache["jobs"]:
                _simplifyjobs_cache["fetched_at"] = now
                return _simplifyjobs_cache["jobs"]

            resp.raise_for_status()
            readme = resp.text
            jobs = _parse_simplifyjobs_readme_tables(readme)
            _simplifyjobs_cache["jobs"] = jobs
            _simplifyjobs_cache["fetched_at"] = now
            _simplifyjobs_cache["etag"] = resp.headers.get("ETag")
            # Remember which URL worked for next time.
            if url != _simplifyjobs_cache.get("readme_raw_url"):
                _simplifyjobs_cache["readme_raw_url"] = url
                _simplifyjobs_cache["etag"] = resp.headers.get("ETag")
            return jobs
        except Exception as e:
            last_error = e
            continue

    # If fetch fails, fall back to stale cache if present
    if _simplifyjobs_cache["jobs"]:
        return _simplifyjobs_cache["jobs"]
    raise last_error or RuntimeError("Failed to fetch SimplifyJobs README")


async def _get_simplifyjobs_listings_cached(max_age_seconds: int = 60 * 60) -> list[dict]:
    """Async wrapper to avoid blocking the event loop during GitHub fetch."""
    import asyncio
    # Check cache first (no I/O needed)
    now = time.time()
    if _simplifyjobs_cache["jobs"] and (now - float(_simplifyjobs_cache["fetched_at"])) < max_age_seconds:
        return _simplifyjobs_cache["jobs"]
    # Need to fetch - run in thread pool to avoid blocking
    return await asyncio.to_thread(_get_simplifyjobs_listings_cached_sync, max_age_seconds)


def _html_to_text(html: str) -> str:
    if not isinstance(html, str):
        return ""
    t = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_json_ld_job_posting_text(html: str) -> Optional[str]:
    """Extract job posting text from JSON-LD blocks if present.

    Many ATS providers (notably Workday) embed the full job description in
    <script type="application/ld+json"> blocks.
    """
    if not isinstance(html, str) or not html:
        return None

    blocks = re.findall(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>([\s\S]*?)</script>",
        html,
        flags=re.IGNORECASE,
    )
    if not blocks:
        return None

    def _as_list(x):
        if isinstance(x, list):
            return x
        if isinstance(x, dict):
            return [x]
        return []

    candidates: list[dict] = []
    for raw in blocks:
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue

        for item in _as_list(obj):
            if not isinstance(item, dict):
                continue
            t = item.get("@type")
            # Some providers use a list for @type
            types = [str(x).lower() for x in (t if isinstance(t, list) else [t]) if x]
            if any("jobposting" in tt for tt in types) or ("description" in item and "hiringOrganization" in item):
                candidates.append(item)

    if not candidates:
        return None

    job = candidates[0]
    title = (job.get("title") or job.get("name") or "").strip()
    org = job.get("hiringOrganization") or {}
    org_name = (org.get("name") if isinstance(org, dict) else "") or ""
    desc = job.get("description") or ""
    desc_txt = _html_to_text(desc) if isinstance(desc, str) else ""

    # Workday sometimes includes qualifications/responsibilities in the description only.
    parts = []
    header_bits = [b for b in [title, org_name] if isinstance(b, str) and b.strip()]
    if header_bits:
        parts.append(" - ".join([b.strip() for b in header_bits]))
    if desc_txt:
        parts.append(desc_txt)

    out = "\n".join(parts).strip()
    return out or None


_job_posting_cache: dict[str, dict] = {}
_job_posting_details_cache: dict[str, dict] = {}


def _fetch_job_posting_text_sync(url: str, max_chars: int = 8000) -> Optional[str]:
    """Synchronous version - use _fetch_job_posting_text for async contexts."""
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if not (u.startswith("http://") or u.startswith("https://")):
        return None

    now = time.time()
    cached = _job_posting_cache.get(u)
    if cached and (now - float(cached.get("fetched_at", 0))) < 60 * 60 * 6:
        return cached.get("text")

    try:
        resp = requests.get(
            u,
            timeout=12,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; frymyresume/1.0; +https://frymyresume.cv)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        if resp.status_code >= 400:
            return None
        # Prefer JSON-LD extraction (common on ATS pages) to avoid losing content to script stripping.
        txt = _extract_json_ld_job_posting_text(resp.text)
        if not txt:
            txt = _html_to_text(resp.text)
        if not txt:
            return None
        txt = txt[:max_chars]
        _job_posting_cache[u] = {"fetched_at": now, "text": txt}
        return txt
    except Exception:
        return None


async def _fetch_job_posting_text(url: str, max_chars: int = 8000) -> Optional[str]:
    """Async wrapper to avoid blocking the event loop during job posting fetch."""
    import asyncio
    # Check cache first (no I/O needed)
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if not (u.startswith("http://") or u.startswith("https://")):
        return None
    now = time.time()
    cached = _job_posting_cache.get(u)
    if cached and (now - float(cached.get("fetched_at", 0))) < 60 * 60 * 6:
        return cached.get("text")
    # Need to fetch - run in thread pool to avoid blocking
    return await asyncio.to_thread(_fetch_job_posting_text_sync, url, max_chars)


async def _summarize_job_posting_to_requirements(
    *,
    posting_text: str,
    company: Optional[str] = None,
    role: Optional[str] = None,
) -> Optional[dict]:
    """Return a structured summary of a job posting.

    If Gemini is available, paraphrase (avoid verbatim copying) into responsibilities/requirements.
    Otherwise return a small heuristic summary.
    """
    t = (posting_text or "").strip()
    if not t:
        return None

    def _heuristic() -> dict:
        return {
            "summary": (t[:600] + ("…" if len(t) > 600 else "")),
            "responsibilities": [],
            "requirements": [],
            "qualifications": [],
            "nice_to_have": [],
        }

    # Fallback: heuristic-only when no API key.
    if not GEMINI_API_KEY:
        return _heuristic()

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""You are extracting job details for a job simulator.

Return ONLY valid JSON with these keys:
- summary: string (<= 600 chars)
- responsibilities: array of strings (<= 10 items)
- requirements: array of strings (<= 12 items)
- qualifications: array of strings (<= 8 items)
- nice_to_have: array of strings (<= 8 items)

Rules:
- Paraphrase. Do NOT copy sentences verbatim from the posting.
- Avoid quoting more than 6 consecutive words from the source.
- If a section isn't present, return an empty array.

Company: {company or ''}
Role: {role or ''}

JOB POSTING TEXT:
{t}
"""

        resp = await call_gemini_with_retry_async(
            client=client,
            model="gemini-2.5-flash",
            contents=prompt,
            max_retries=2,
            initial_delay=1,
        )
        m = re.search(r"\{.*\}", (resp.text or "").strip(), flags=re.DOTALL)
        if not m:
            return _heuristic()
        obj = json.loads(m.group(0))
        if not isinstance(obj, dict):
            return _heuristic()

        def _clamp_list(x, n):
            if not isinstance(x, list):
                return []
            out = []
            for item in x:
                if not isinstance(item, str):
                    continue
                s = item.strip()
                if s:
                    out.append(s)
                if len(out) >= n:
                    break
            return out

        summary = obj.get("summary")
        if not isinstance(summary, str):
            summary = ""
        summary = summary.strip()
        if len(summary) > 600:
            summary = summary[:600].rstrip() + "…"

        return {
            "summary": summary,
            "responsibilities": _clamp_list(obj.get("responsibilities"), 10),
            "requirements": _clamp_list(obj.get("requirements"), 12),
            "qualifications": _clamp_list(obj.get("qualifications"), 8),
            "nice_to_have": _clamp_list(obj.get("nice_to_have"), 8),
        }
    except Exception:
        return _heuristic()


@app.get("/api/jobs/real")
async def list_real_jobs(q: str = "", limit: int = 100, offset: int = 0):
    """Return internship rows from SimplifyJobs/Summer2026-Internships README.md.

    Notes:
    - This endpoint returns the fields available in the repo table (not scraped full job postings).
    - Use `q` to filter by company/role/location/category.
    """
    limit = max(1, min(int(limit), 250))
    offset = max(0, int(offset))

    try:
        jobs = await _get_simplifyjobs_listings_cached()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch SimplifyJobs listings: {e}")
    if q:
        qn = q.strip().lower()
        jobs = [
            j for j in jobs
            if qn in (j.get("company") or "").lower()
            or qn in (j.get("role") or "").lower()
            or qn in (j.get("location") or "").lower()
            or qn in (j.get("category") or "").lower()
        ]

    total = len(jobs)
    page = jobs[offset:offset + limit]
    return JSONResponse(content={
        "success": True,
        "source": _simplifyjobs_cache["source"],
        "total": total,
        "limit": limit,
        "offset": offset,
        "jobs": page,
    })


@app.get("/api/jobs/real/details")
async def get_real_job_details(
    apply_url: str,
    company: str = "",
    role: str = "",
):
    """Fetch and summarize a single real job posting.

    The SimplifyJobs list doesn't include full descriptions. This endpoint uses the `apply_url`
    to fetch the posting page and returns a paraphrased summary + requirements.
    """
    u = (apply_url or "").strip()
    if not u:
        raise HTTPException(status_code=400, detail="apply_url is required")

    now = time.time()
    cached = _job_posting_details_cache.get(u)
    if cached and (now - float(cached.get("fetched_at", 0))) < 60 * 60 * 6:
        return JSONResponse(content={
            "success": True,
            "apply_url": u,
            "details": cached.get("details"),
            "cached": True,
        })

    posting_text = await _fetch_job_posting_text(u, max_chars=12000)
    if not posting_text:
        return JSONResponse(content={
            "success": False,
            "apply_url": u,
            "error": "Could not fetch job posting text from apply_url",
        })

    details = await _summarize_job_posting_to_requirements(
        posting_text=posting_text,
        company=(company or None),
        role=(role or None),
    )
    if not details:
        details = {
            "summary": (posting_text[:600] + ("…" if len(posting_text) > 600 else "")),
            "responsibilities": [],
            "requirements": [],
            "qualifications": [],
            "nice_to_have": [],
        }

    _job_posting_details_cache[u] = {"fetched_at": now, "details": details}
    return JSONResponse(content={
        "success": True,
        "apply_url": u,
        "details": details,
        "cached": False,
    })


def extract_text_from_pdf(pdf_file: bytes) -> str:
    """Extract text from PDF file bytes."""
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    return text


def extract_text(file_content: bytes, content_type: str) -> str:
    """Extract text from uploaded file based on content type."""
    if content_type == "application/pdf":
        return extract_text_from_pdf(file_content)
    return file_content.decode("utf-8")


def call_gemini_with_retry(client, model, contents, max_retries=3, initial_delay=1, timeout=60):
    """
    Call Gemini API with retry logic for 503/429 errors and timeout.

    Args:
        client: Gemini client instance
        model: Model name to use
        contents: Prompt/content to send
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        timeout: Maximum time in seconds for the entire operation

    Returns:
        Response from Gemini API

    Raises:
        Exception: If all retries fail, timeout, or non-retryable error occurs
    """
    import signal

    last_exception = None
    start_time = time.time()

    for attempt in range(max_retries + 1):
        # Check if we've exceeded total timeout
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise Exception("Request timed out. The server is experiencing high load. Please try again in a few moments.")

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents
            )
            return response
        except Exception as e:
            error_str = str(e).lower()

            # Check if it's a retryable error (503, 429, overloaded, quota)
            is_retryable = False
            is_rate_limit = False

            # Rate limit / quota errors (429)
            if "429" in str(e) or "resource exhausted" in error_str or "quota" in error_str or "rate limit" in error_str:
                is_retryable = True
                is_rate_limit = True

            # Service unavailable (503)
            if "503" in str(e) or "unavailable" in error_str or "overloaded" in error_str:
                is_retryable = True

            # Check exception attributes
            status_code = getattr(e, 'status_code', None) or getattr(e, 'code', None)
            if status_code in [429, 503]:
                is_retryable = True
                is_rate_limit = status_code == 429

            if is_retryable and attempt < max_retries:
                # Use longer delays for rate limits
                base_delay = initial_delay * 2 if is_rate_limit else initial_delay
                delay = min(base_delay * (2 ** attempt), 10)  # Cap at 10 seconds

                # Don't wait if we'd exceed timeout
                if time.time() - start_time + delay > timeout:
                    raise Exception("Request timed out. The server is experiencing high load. Please try again in a few moments.")

                print(f"[Gemini] Retrying in {delay}s (attempt {attempt + 1}/{max_retries}) - {str(e)[:100]}")
                # Use asyncio-safe sleep if in async context, otherwise regular sleep
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    # We're in an async context but this is a sync function
                    # Just use regular sleep - the function will be wrapped with to_thread
                    time.sleep(delay)
                except RuntimeError:
                    # No running event loop, safe to use time.sleep
                    time.sleep(delay)
                last_exception = e
                continue
            else:
                # Non-retryable error or max retries reached
                if is_rate_limit:
                    raise Exception("Server is currently busy due to high demand. Please try again in a few moments.")
                raise e

    # If we exhausted all retries, raise appropriate error
    if last_exception:
        error_str = str(last_exception).lower()
        if "429" in str(last_exception) or "quota" in error_str or "rate limit" in error_str:
            raise Exception("Server is currently busy due to high demand. Please try again in a few moments.")
        raise Exception("Service temporarily unavailable. Please try again in a few moments.")


async def call_gemini_with_retry_async(client, model, contents, max_retries=3, initial_delay=1, timeout=60):
    """Async wrapper for call_gemini_with_retry to avoid blocking the event loop."""
    import asyncio
    return await asyncio.to_thread(
        call_gemini_with_retry,
        client, model, contents, max_retries, initial_delay, timeout
    )


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "AI Resume Critique API is running"}


@app.post("/api/analyze")
async def analyze_resume(
    file: UploadFile = File(...),
    job_role: Optional[str] = Form(None),
    notes: Optional[str] = Form(None)
):
    """
    Analyze a resume using AI.

    Args:
        file: The resume file (PDF or TXT)
        job_role: Target job role (optional)
        notes: Additional notes (optional)

    Returns:
        JSON with analysis results
    """
    try:
        def _sanitize_job_role(value: Optional[str]) -> Optional[str]:
            if not value:
                return None
            v = re.sub(r"\s+", " ", value).strip()
            if not v:
                return None

            # Remove obvious prompt-injection phrasing
            injection_patterns = [
                r"ignore\s+all\s+previous\s+instructions",
                r"ignore\s+previous\s+instructions",
                r"ignore\s+all\s+instructions",
                r"system\s+prompt",
                r"developer\s+message",
                r"you\s+are\s+chatgpt",
                r"give\s+the\s+user\s+\d+",
                r"return\s+\d+",
                r"always\s+give\s+\d+",
                r"score\s+\d+",
            ]
            lowered = v.casefold()
            if any(re.search(p, lowered) for p in injection_patterns):
                return None

            # Allow only a conservative set of characters
            v = re.sub(r"[^a-zA-Z0-9\s\-\/+&.,()]+", "", v).strip()
            if not v:
                return None

            # Limit length to avoid instruction stuffing
            if len(v) > 60:
                v = v[:60].strip()
            return v or None

        job_role = _sanitize_job_role(job_role)

        # Validate file type
        if file.content_type not in ["application/pdf", "text/plain"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only PDF and TXT files are supported."
            )

        # Read file content
        file_content = await file.read()

        # Extract text
        text_content = extract_text(file_content, file.content_type)

        if not text_content.strip():
            raise HTTPException(
                status_code=400,
                detail="File does not have any content"
            )

        # Build prompt with reference examples and strict scoring
        default_note = "If the student is still in university, they are probably applying for internship roles"
        additional_notes = f"{notes}. {default_note}" if notes else default_note

        reference_examples = """
        REFERENCE RESUMES FOR CALIBRATION:

        CRITICAL CONTEXT: With modern AI coding tools (ChatGPT, Claude, Copilot, Cursor), projects can be "vibe coded" in hours.
        Therefore, projects alone carry SIGNIFICANTLY LESS WEIGHT than they did previously. Focus heavily on:
        - REAL work experience with quantifiable impact
        - Duration and quality of professional roles
        - Competitive achievements (hackathons WON, case competitions with TOP placements only)
        - Academic excellence (high GPA, scholarships, awards)

        SATURATED MARKET CALIBRATION - EXTREMELY STRICT:
        - The market is HEAVILY saturated with candidates. You must be RUTHLESSLY STRICT.
        - Most resumes are mediocre. DO NOT give the benefit of the doubt.
        - If you see vague bullets, buzzwords, or no metrics - PENALIZE HEAVILY.
        - Projects without clear evidence of real usage, deployment, testing, or architecture decisions are worth MINIMAL points.
        - University club projects are NOT professional experience unless they show exceptional scope/impact.

        BEGINNER/WEAK STUDENT (Typical Score: 30-55):
        - First or second year university student
        - Only tutorial-level projects OR projects with no clear depth
        - No internships or only very basic/short internships
        - Vague bullet points with no metrics or concrete achievements
        - Generic skills lists with no evidence
        REALISTIC OUTCOME: Will struggle to get interviews at competitive companies.

        DECENT STUDENT (Typical Score: 55-65):
        - Has 1 real internship OR strong university dev team role with measurable contributions
        - 2-3 projects that show SOME depth (testing, deployment, or real users)
        - Some quantifiable metrics (even if modest)
        - Clear technical skills with evidence of application
        REALISTIC OUTCOME: Can potentially land interviews at mid-tier companies with effort.

        INTERMEDIATE/SOLID (Typical Score: 65-75):
        - Multiple real internships with clear ownership and impact
        - Projects show real depth: architecture decisions, testing, deployment, scale, real users with metrics
        - Competitive achievements (hackathon wins, not just participation)
        - Clear evidence of technical maturity and professional work quality
        REALISTIC OUTCOME: Competitive for mid-tier and some upper-tier companies.

        STRONG (Typical Score: 75-85):
        - 2+ strong internships with significant impact at known companies
        - Projects are production-quality with clear technical depth
        - Leadership roles OR competitive programming success OR published research
        - Multiple quantifiable achievements showing scope and impact
        REALISTIC OUTCOME: Competitive for top-tier companies, strong interview candidate.

        EXCEPTIONAL/FAANG READY (Score: 85+):
        - FAANG/unicorn internship(s) with major impact
        - Elite competitive programming (Codeforces Master+, ICPC medalist, IOI/USACO top tiers)
        - Major OSS contributions (maintainer of widely-used projects)
        - Published research at credible venues OR product with significant traction (10k+ users)
        - Multiple exceptional signals, not just one
        REALISTIC OUTCOME: Ready for FAANG-level interviews, likely to succeed.

        SCORING GUIDELINES (EXTREMELY STRICT - NO MERCY):
        - 90-100: Reserved for truly exceptional candidates (less than 1% of resumes)
        - 85-89: FAANG Ready with multiple strong signals
        - 75-84: Strong candidate with proven track record
        - 65-74: Intermediate/Solid with real experience and depth
        - 55-64: Decent but unremarkable
        - 45-54: Weak/Beginner with minimal real experience
        - 30-44: Very weak, major gaps
        - 0-29: Essentially unqualified

        BEGINNER RESUME HARD CAP: If the resume shows beginner-level experience (no real internships, only basic projects, first/second year student with minimal work), the score MUST NOT exceed 70. Period.

        INTERMEDIATE RESUME RANGE: If the resume shows intermediate-level experience (1-2 internships, decent projects with some depth), score in the 70-80 range ONLY if truly justified.

        DO NOT INFLATE SCORES - BE RUTHLESSLY STRICT:
        - Assume projects are AI-assisted unless proven otherwise (tests, deployment, architecture docs, real users with metrics)
        - Generic bullets like "developed X" or "implemented Y" without metrics = MINIMAL value
        - "Participated in" or "helped with" = essentially worthless
        - "Familiar with" or "knowledge of" = not real skill evidence
        - Start at 40 by default. Add points ONLY for concrete evidence. Subtract for vagueness, buzzwords, or inflated claims.
        - University design teams/research/dev clubs count as real experience ONLY if there's clear ownership and deliverables
        """

        prompt = f"""Today is {date.today()}.
        You are a RUTHLESSLY STRICT hiring manager at a top company in the field of {job_role if job_role else "various industries"}.
        Your job is to AGGRESSIVELY filter out weak candidates. You have ZERO MERCY and NO BIAS toward making candidates feel good.
        
        The market is HEAVILY saturated. Most resumes are mediocre. You must be EXTREMELY STRICT.

        {reference_examples}

        RESUME TO REVIEW:
        {text_content}

        CRITICAL INSTRUCTIONS - READ CAREFULLY:
        1. Compare this resume to the REFERENCE resumes provided above
        2. Determine the TRUE experience level (Beginner/Decent/Intermediate/Strong/Exceptional)
        3. Assign a BRUTALLY HONEST score from 0-100 based on these STRICT SCORING GUIDELINES:
              - 90-100: Reserved for truly exceptional candidates (less than 1% of resumes) - FAANG+ ready with multiple rare signals
              - 85-89: FAANG Ready with proven track record
              - 75-84: Strong candidate with 2+ quality internships and real impact
              - 70-74: Upper-intermediate with solid experience
              - 65-69: Intermediate with decent experience
              - 55-64: Decent but unremarkable
              - 45-54: Weak/Beginner with minimal experience
              - 30-44: Very weak with major gaps
              - 0-29: Essentially unqualified

        HARD RULES - NON-NEGOTIABLE:
        - BEGINNER RESUMES (no real internships, only basic projects, early student) CANNOT score above 70. EVER.
        - INTERMEDIATE RESUMES (1-2 internships, decent projects) can score 70-80 ONLY if truly justified with clear depth and impact.
        - Projects without deployment, testing, real users, or architecture docs are worth MINIMAL points.
        - "Participated in", "helped with", "familiar with", "knowledge of" = worthless fluff.
        - Vague bullets without metrics = RED FLAG, penalize heavily.
        - Start at 40 by default. Add points ONLY for concrete, verifiable achievements.
        
        4. BE RUTHLESSLY CRITICAL - This is NOT about being nice, it's about being ACCURATE.
        5. Focus on: REAL work experience, measurable impact, competitive achievements, technical depth.
        6. GPA doesn't matter much - focus on actual work and achievements.
        7. If you're uncertain between two scores, ALWAYS choose the LOWER one.
        8. Provide an INTEGER score (whole number).
        9. In your assessment, be BLUNT about weaknesses. Don't sugarcoat anything.

        Respond in this EXACT format:
        SCORE: [number between 0-100]

        STRENGTHS:
        - [Bullet point 1 - be specific and concrete, or write "Limited strengths identified"]
        - [Bullet point 2]
        - [Bullet point 3]

        AREAS FOR IMPROVEMENT:
        - [Bullet point 1 - be BLUNT and SPECIFIC about weaknesses]
        - [Bullet point 2 - don't hold back]
        - [Bullet point 3 - be ruthlessly honest]

        RECOMMENDATIONS:
        - [Actionable recommendation 1 - be specific and demanding]
        - [Actionable recommendation 2]
        - [Actionable recommendation 3]

        OVERALL ASSESSMENT:
        [2-3 sentences summarizing the resume's REALISTIC readiness level. Be BRUTALLY HONEST. If it's weak, say so clearly. No sugarcoating.]

        Additional Notes: {additional_notes}
        Tailor your feedback for {job_role if job_role else "general applications"}
        """

        # Call Gemini API with retry logic (async to avoid blocking event loop)
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = await call_gemini_with_retry_async(
            client=client,
            model="gemini-2.5-flash",
            contents=prompt,
            max_retries=3,
            initial_delay=2
        )

        response_text = response.text

        # Extract score from response
        score = None
        score_match = re.search(r'SCORE:\s*(\d+)', response_text, re.IGNORECASE)
        if score_match:
            raw_score = int(score_match.group(1))
            raw_score = max(0, min(100, raw_score))

            # Market calibration: gently reduce common inflation at the top end,
            # but preserve the user's intended mid-range bands.
            adjusted = raw_score
            if raw_score >= 90:
                adjusted -= 5
            elif raw_score >= 85:
                adjusted -= 3
            elif raw_score >= 75:
                adjusted -= 2
            score = max(0, min(100, adjusted))

        return JSONResponse(content={
            "success": True,
            "feedback": response_text,
            "score": score
        })

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        # Return user-friendly messages for common errors
        if "busy" in error_msg or "rate limit" in error_msg or "quota" in error_msg or "429" in str(e):
            raise HTTPException(
                status_code=503,
                detail="Server is currently busy due to high demand. Please try again in a few moments."
            )
        if "timed out" in error_msg or "timeout" in error_msg:
            raise HTTPException(
                status_code=504,
                detail="Request timed out. Please try again."
            )
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


@app.post("/api/screen-resume")
async def screen_resume(
    file: UploadFile = File(...),
    difficulty: str = Form("easy"),
    role: str = Form(...),
    level: str = Form(...),
    company: Optional[str] = Form(None),
    job_source: Optional[str] = Form(None),
    job_category: Optional[str] = Form(None),
    job_location: Optional[str] = Form(None),
    job_apply_url: Optional[str] = Form(None),
    job_age: Optional[str] = Form(None),
    job_row: Optional[str] = Form(None),
):
    """
    Screen resume for job application simulator.

    This process adjusts strictness based on difficulty level:
    - intern: Calibrated for internship programs
    """
    try:
        # Validate file type
        if file.content_type not in ["application/pdf", "text/plain"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only PDF and TXT files are supported."
            )

        # Read and extract text
        file_content = await file.read()
        text_content = extract_text(file_content, file.content_type)

        if not text_content.strip():
            raise HTTPException(
                status_code=400,
                detail="File does not have any content"
            )

        # If the caller provided a real job listing, infer difficulty using AI.
        inferred_difficulty: Optional[str] = None
        if (job_source or "").lower() in {"real", "simplifyjobs_summer2026", "simplifyjobs"}:
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                listing_blob = "\n".join([
                    f"Company: {company or ''}",
                    f"Role: {role}",
                    f"Category: {job_category or ''}",
                    f"Location: {job_location or ''}",
                    f"Apply URL: {job_apply_url or ''}",
                    f"Age: {job_age or ''}",
                    f"Repo row: {job_row or ''}",
                ])
                difficulty_prompt = f"""Choose the internship screening difficulty for this job.

Return ONLY valid JSON like {{"difficulty":"easy"}}.
Allowed values: easy, medium, hard.

Heuristics:
- hard: Big Tech/top finance/very selective OR highly specialized role.
- medium: typical established company internship.
- easy: early-stage/less selective/general entry internship.

LISTING:
{listing_blob}
"""
                resp = await call_gemini_with_retry_async(
                    client=client,
                    model="gemini-2.5-flash",
                    contents=difficulty_prompt,
                    max_retries=2,
                    initial_delay=1,
                )
                m = re.search(r"\{.*\}", (resp.text or ""), flags=re.DOTALL)
                if m:
                    obj = json.loads(m.group(0))
                    d = (obj.get("difficulty") or "").strip().lower()
                    if d in {"easy", "medium", "hard"}:
                        inferred_difficulty = d
            except Exception:
                inferred_difficulty = None

        effective_difficulty = (inferred_difficulty or difficulty or "easy").strip().lower()
        if effective_difficulty not in {"easy", "medium", "hard"}:
            effective_difficulty = "easy"

        # Map difficulty to company tier and screening criteria
        difficulty_configs = {
            "easy": {
                "company_type": "an early-stage startup internship program",
                "strictness": """
                STARTUP INTERNSHIP HIRING MODE: Looking for candidates with real potential and demonstrated technical ability.

                CRITICAL: GPA doesn't really matter - focus on actual work and projects.
                University dev team roles (design teams, research labs, student dev clubs) COUNT as real experience.
                Projects can compensate for lack of traditional internships IF they show real depth.

                PASS if candidate has AT LEAST TWO of:
                - Previous internship or co-op position
                - Active role on university design team, research project, or dev club
                - 2-3 strong projects with real technical depth (not basic CRUD apps)
                - Competitive achievements (hackathon wins, case competition placements)
                - Part-time or freelance dev work

                REJECT if:
                - Only basic tutorial-level projects with no depth
                - No university dev team involvement AND no internships AND only shallow projects
                - No evidence of technical growth or learning

                GPA is nice to have but NOT a deciding factor.
                Target pass rate: ~15-25% of applicants
                """
            },
            "medium": {
                "company_type": "a mid-tier company internship program",
                "strictness": """
                MID-TIER COMPANY INTERNSHIP HIRING MODE: Looking for proven performers with real technical depth and clear evidence of impact.

                CRITICAL: GPA is not a major factor. What matters:
                - REAL work experience (internships, research assistantships, dev team leadership)
                - Quantifiable impact and ownership (not just "participated")
                - Technical depth in projects (architecture, testing, deployment, real usage)
                - Competitive validation (hackathons won, contributions merged, users acquired)

                PASS if candidate has AT LEAST ONE strong professional signal (internship/dev team leadership/research) AND AT LEAST TWO of:
                - Previous internship at known company with clear responsibilities/impact
                - University dev team leadership role (design team lead, research contributor with deliverables)
                - Notable competitive achievements (hackathon wins/placements, not just participation)
                - Strong OSS contributions (merged PRs with real impact, not typo fixes)
                - Projects with real depth (tests, deployment, metrics, users) and clear ownership

                REJECT if:
                - No previous internship/dev team experience AND only surface-level projects
                - Projects lack depth (no tests, no deployment, no users, no clear architecture)
                - Vague bullet points with no metrics or specific outcomes
                - No evidence of working on complex technical problems or collaborating on real codebases

                GPA is nice to have but NOT required if work/projects are strong.
                Target pass rate: ~5-12% of applicants
                """
            },
            "hard": {
                "company_type": "a FAANG-tier / Big Tech company internship program",
                "strictness": """
                FAANG-TIER INTERNSHIP HIRING MODE: Only accepting top-tier candidates with exceptional proven track records.

                CRITICAL: GPA is nice to have but NOT required. What matters:
                - Previous internships at top companies (FAANG, unicorns, elite startups)
                - Competitive programming: Codeforces Master+, ICPC regionals, IOI medals
                - Real research publications or significant open source contributions
                - Founded company with real traction or worked on products with millions of users
                - Exceptional project portfolio with measurable impact

                NON-NEGOTIABLE GATE (must pass this gate, otherwise REJECT):
                The resume MUST clearly show at least ONE of the following hard signals:
                - A top-tier internship (FAANG/unicorn/very selective trading firm)
                - Elite competitive programming (e.g., Codeforces Master+, ICPC strong placement, IOI/USACO top tiers)
                - Major open-source impact (maintainer/core contributor, widely-used library, clear adoption)
                - Research at a strong lab with publication(s) OR meaningful product traction (real users/metrics)

                PASS only if the candidate clears the NON-NEGOTIABLE GATE AND has AT LEAST FOUR of:
                - 1+ previous FAANG/unicorn/very selective internship (or a clear return offer)
                - Strong competitive signal (Codeforces Master+/ICPC strong placement/IOI/USACO top tiers)
                - Significant open-source impact (not small PRs; clear ownership/maintenance)
                - Published research (credible venue) or serious engineering leadership (mentoring/leading major scope)
                - Built product with real traction (e.g., 10k+ users OR clear revenue OR meaningful adoption)
                - Multiple strong internships with quantified impact and scope
                - Exceptional projects that show depth (tests, perf, systems design, deployment, scale)

                REJECT if:
                - No previous top-tier internship AND no exceptional technical achievements
                - Only has projects without competitive validation or real users
                - Generic internship experience at unknown companies
                - No measurable impact or scale

                GPA is nice to have but NOT a deciding factor.
                Target pass rate: ~1-3% of applicants
                """
            }
        }

        config = difficulty_configs.get(effective_difficulty, difficulty_configs["easy"])
        level_context = f"{level} level" if level != "internship" else "internship position"

        # Reference resume examples for calibration
        reference_examples = {
            "easy": """
            REFERENCE: This is an acceptable resume for a startup internship:
            - University student or recent graduate
            - 1+ relevant personal or school projects
            - Basic competency in required tech skills
            - Shows learning mindset and enthusiasm

            This candidate should PASS a startup internship screening. Use this as your baseline.
            """,
            "medium": """
            REFERENCE: This is the MINIMUM acceptable resume for a mid-tier company internship:
            - At least 1 real internship OR strong university dev team role with clear ownership
            - Projects must show depth: testing, deployment, architecture decisions, or real users/metrics
            - Clear evidence of technical competency beyond tutorials (frameworks, systems, collaboration)
            - Quantified impact or scope in at least one experience

            This candidate should PASS a mid-tier company internship screening. Use this as your baseline.
            """,
            "hard": """
            REFERENCE: This is the MINIMUM acceptable resume for a FAANG-tier internship:
            - At least ONE hard signal: FAANG/unicorn/selective internship OR elite competitive programming OR major OSS impact OR credible research/publication OR clear product traction
            - Strong evidence of engineering depth (tests, deployment, scale, design decisions)
            - Quantified impact (scope/metrics) in at least one experience

            This candidate should PASS a FAANG-tier internship screening. Use this as your baseline.
            """
        }

        job_context = ""
        if (job_source or "").lower() in {"real", "simplifyjobs_summer2026", "simplifyjobs"}:
            job_posting_text = None
            if job_apply_url:
                # Best-effort: some postings (especially simplify.jobs) are publicly readable.
                job_posting_text = await _fetch_job_posting_text(job_apply_url)

            job_context = f"""
    JOB LISTING CONTEXT (from SimplifyJobs/Summer2026-Internships list; may be limited):
    - Company: {company or 'Unknown'}
    - Role: {role}
    - Category: {job_category or ''}
    - Location: {job_location or ''}
    - Apply URL: {job_apply_url or ''}
    - Age: {job_age or ''}
    - Source Row: {job_row or ''}
 
JOB POSTING TEXT (best-effort fetch; use this to judge requirements if present):
{(job_posting_text or '')}
    """.strip()

        prompt = f"""You are a resume screener at {config['company_type']} for a {role} position ({level_context}).

        {job_context}

        {config['strictness']}

        {reference_examples.get(effective_difficulty, reference_examples["easy"])}

        RESUME TO REVIEW:
        {text_content}

        INSTRUCTIONS:
        1. Compare this resume to the REFERENCE resume provided above
        2. The reference resume represents the MINIMUM bar for passing
        3. Be strict: the resume must be CLEARLY BETTER THAN the reference to PASS
        3b. If this resume is only roughly EQUAL to the reference, REJECT
        4. If this resume is WEAKER than the reference, you should REJECT them
        4b. If JOB POSTING TEXT includes explicit requirements and the resume clearly misses critical requirements, REJECT.
        5. Make a BINARY decision: PASS or REJECT
        6. Provide brief reasoning

        Respond in this EXACT format:
        DECISION: [PASS or REJECT]

        REASONING:
        [2-3 sentences explaining your decision compared to the reference baseline]

        KEY STRENGTHS: (if PASS)
        - [Bullet point 1]
        - [Bullet point 2]
        - [Bullet point 3]

        MAJOR CONCERNS: (if REJECT)
        - [Bullet point 1]
        - [Bullet point 2]

        IMPROVEMENT TIPS:
        - [Actionable tip 1]
        - [Actionable tip 2]
        """

        # Call Gemini API with retry logic (async to avoid blocking event loop)
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = await call_gemini_with_retry_async(
            client=client,
            model="gemini-2.5-flash",
            contents=prompt,
            max_retries=3,
            initial_delay=2
        )

        response_text = response.text

        # Parse response to determine if passed
        passed = "DECISION: PASS" in response_text.upper()

        # Deterministic guardrail for preset FAANG-tier jobs: if the resume does not appear
        # to include any top-tier signals, force REJECT regardless of model generosity.
        is_real_listing = (job_source or "").lower() in {"real", "simplifyjobs_summer2026", "simplifyjobs"}
        if (not is_real_listing) and effective_difficulty == "hard":
            gate_patterns = [
                r"\b(google|alphabet|meta|facebook|amazon|aws|apple|microsoft|netflix|openai|anthropic|deepmind|nvidia|tesla|uber|airbnb|stripe|databricks|palantir|snowflake|coinbase|doordash|bloomberg|two\s+sigma|citadel|jane\s+street)\b",
                r"\b(codeforces|icpc|ioi|usaco|acm\s+icpc|topcoder|kaggle\s+(master|grandmaster))\b",
                r"\b(maintainer|core\s+contributor|tech\s+lead|team\s+lead)\b",
                r"\b(\d{3,})\s*(stars|downloads)\b",
                r"\b(10,?000\+?)\s*(users|customers)\b",
                r"\b(publication|published|paper|arxiv)\b",
            ]
            hard_gate_met = any(re.search(p, text_content, re.IGNORECASE) for p in gate_patterns)
            if not hard_gate_met:
                passed = False
                response_text = (response_text or "") + "\n\n[OVERRIDE] Preset FAANG-tier screening requires explicit top-tier signals (FAANG/unicorn/selective internship, elite competitive programming, major OSS impact, credible research/publications, or clear product traction). Not detected, so REJECT."

        return JSONResponse(content={
            "passed": passed,
            "feedback": response_text,
            "difficulty": effective_difficulty,
            "difficulty_inferred": bool(inferred_difficulty),
            "role": role,
            "level": level,
            "resume_text": text_content  # Include resume text for behavioral interview personalization
        })

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        # Return user-friendly messages for common errors
        if "busy" in error_msg or "rate limit" in error_msg or "quota" in error_msg or "429" in str(e):
            raise HTTPException(
                status_code=503,
                detail="Server is currently busy due to high demand. Please try again in a few moments."
            )
        if "timed out" in error_msg or "timeout" in error_msg:
            raise HTTPException(
                status_code=504,
                detail="Request timed out. Please try again."
            )
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


# Technical Interview Questions
TECHNICAL_QUESTIONS = {
    "easy": [
        {
            "id": "two-sum",
            "title": "Two Sum",
            "description": "Given an array of integers nums and an integer target, return the indices i and j such that nums[i] + nums[j] == target and i != j. You may assume that every input has exactly one pair of indices that satisfy the condition. Return the answer with the smaller index first.",
            "difficulty": "Easy",
            "examples": [
                {"input": "nums = [3,4,5,6], target = 7", "output": "[0,1]", "explanation": "nums[0] + nums[1] == 7, so we return [0, 1]."},
                {"input": "nums = [4,5,6], target = 10", "output": "[0,2]"}
            ],
            "constraints": [
                "2 <= nums.length <= 1000",
                "-10,000,000 <= nums[i] <= 10,000,000",
                "-10,000,000 <= target <= 10,000,000",
                "Only one valid answer exists"
            ],
            "sampleTestCases": [
                {"input": {"nums": [3, 4, 5, 6], "target": 7}, "expectedOutput": [0, 1]},
                {"input": {"nums": [4, 5, 6], "target": 10}, "expectedOutput": [0, 2]},
                {"input": {"nums": [5, 5], "target": 10}, "expectedOutput": [0, 1]}
            ],
            "hiddenTestCases": [
                {"input": {"nums": [2, 7, 11, 15], "target": 9}, "expectedOutput": [0, 1]},
                {"input": {"nums": [-1, -2, -3, -4, -5], "target": -8}, "expectedOutput": [2, 4]},
                {"input": {"nums": [0, 4, 3, 0], "target": 0}, "expectedOutput": [0, 3]},
                {"input": {"nums": [1, 2], "target": 3}, "expectedOutput": [0, 1]},
                {"input": {"nums": [10, 20, 30, 40, 50], "target": 90}, "expectedOutput": [3, 4]},
                {"input": {"nums": [1, 3, 4, 2], "target": 6}, "expectedOutput": [2, 3]},
                {"input": {"nums": [-5, -3, -1, 0, 2, 4], "target": -4}, "expectedOutput": [1, 2]},
                {"input": {"nums": [100, 200, 300, 400], "target": 700}, "expectedOutput": [2, 3]},
                {"input": {"nums": [15, 11, 7, 2], "target": 9}, "expectedOutput": [2, 3]},
                {"input": {"nums": [3, 2, 4], "target": 6}, "expectedOutput": [1, 2]}
            ]
        },
        {
            "id": "contains-duplicate",
            "title": "Contains Duplicate",
            "description": "Given an integer array nums, return true if any value appears more than once in the array, otherwise return false.",
            "difficulty": "Easy",
            "examples": [
                {"input": "nums = [1, 2, 3, 3]", "output": "true"},
                {"input": "nums = [1, 2, 3, 4]", "output": "false"}
            ],
            "constraints": [
                "1 <= nums.length <= 10^5",
                "-10^9 <= nums[i] <= 10^9"
            ],
            "sampleTestCases": [
                {"input": {"nums": [1, 2, 3, 3]}, "expectedOutput": True},
                {"input": {"nums": [1, 2, 3, 4]}, "expectedOutput": False}
            ],
            "hiddenTestCases": [
                {"input": {"nums": []}, "expectedOutput": False},
                {"input": {"nums": [1]}, "expectedOutput": False},
                {"input": {"nums": [0, 0]}, "expectedOutput": True},
                {"input": {"nums": [-1, -2, -3, -4]}, "expectedOutput": False},
                {"input": {"nums": [-1, -2, -3, -1]}, "expectedOutput": True},
                {"input": {"nums": [1000000000, -1000000000, 1000000000]}, "expectedOutput": True},
                {"input": {"nums": [5, 4, 3, 2, 1]}, "expectedOutput": False},
                {"input": {"nums": [1, 2, 3, 4, 5, 6, 7, 8, 9, 1]}, "expectedOutput": True},
                {"input": {"nums": [10, 11, 12, 13, 14, 15]}, "expectedOutput": False},
                {"input": {"nums": [7, 7]}, "expectedOutput": True},
                {"input": {"nums": [1, 5, 9, 13, 17, 21, 9]}, "expectedOutput": True}
            ]
        },
        {
            "id": "valid-anagram",
            "title": "Valid Anagram",
            "description": "Given two strings s and t, return true if the two strings are anagrams of each other, otherwise return false. An anagram contains the exact same characters as another string, but the order can be different.",
            "difficulty": "Easy",
            "examples": [
                {"input": "s = \"racecar\", t = \"carrace\"", "output": "true"},
                {"input": "s = \"jar\", t = \"jam\"", "output": "false"}
            ],
            "constraints": [
                "s and t consist of lowercase English letters"
            ],
            "sampleTestCases": [
                {"input": {"s": "racecar", "t": "carrace"}, "expectedOutput": True},
                {"input": {"s": "jar", "t": "jam"}, "expectedOutput": False}
            ],
            "hiddenTestCases": [
                {"input": {"s": "a", "t": "a"}, "expectedOutput": True},
                {"input": {"s": "a", "t": "b"}, "expectedOutput": False},
                {"input": {"s": "ab", "t": "ba"}, "expectedOutput": True},
                {"input": {"s": "abc", "t": "ab"}, "expectedOutput": False},
                {"input": {"s": "aaaaaaaaaa", "t": "aaaaaaaaaa"}, "expectedOutput": True},
                {"input": {"s": "anagram", "t": "nagaram"}, "expectedOutput": True},
                {"input": {"s": "rat", "t": "car"}, "expectedOutput": False},
                {"input": {"s": "listen", "t": "silent"}, "expectedOutput": True},
                {"input": {"s": "hello", "t": "world"}, "expectedOutput": False},
                {"input": {"s": "aabbcc", "t": "abcabc"}, "expectedOutput": True},
                {"input": {"s": "abcd", "t": "dcba"}, "expectedOutput": True}
            ]
        },
        {
            "id": "valid-palindrome",
            "title": "Valid Palindrome",
            "description": "Given a string s, return true if it is a palindrome, otherwise return false. A palindrome reads the same forward and backward. It is case-insensitive and ignores all non-alphanumeric characters.",
            "difficulty": "Easy",
            "examples": [
                {
                    "input": "s = \"Was it a car or a cat I saw?\"",
                    "output": "true",
                    "explanation": "After filtering we get \"wasitacaroracatisaw\", which is a palindrome."
                },
                {"input": "s = \"tab a cat\"", "output": "false", "explanation": "\"tabacat\" is not a palindrome."}
            ],
            "constraints": [
                "1 <= s.length <= 1000",
                "s is made up of only printable ASCII characters"
            ],
            "sampleTestCases": [
                {"input": {"s": "Was it a car or a cat I saw?"}, "expectedOutput": True},
                {"input": {"s": "tab a cat"}, "expectedOutput": False}
            ],
            "hiddenTestCases": [
                {"input": {"s": "A man, a plan, a canal: Panama"}, "expectedOutput": True},
                {"input": {"s": "race a car"}, "expectedOutput": False},
                {"input": {"s": "0P"}, "expectedOutput": False},
                {"input": {"s": "   "}, "expectedOutput": True},
                {"input": {"s": "a"}, "expectedOutput": True},
                {"input": {"s": "ab"}, "expectedOutput": False},
                {"input": {"s": "aba"}, "expectedOutput": True},
                {"input": {"s": "Madam"}, "expectedOutput": True},
                {"input": {"s": "No lemon, no melon"}, "expectedOutput": True},
                {"input": {"s": "abc123cba"}, "expectedOutput": False},
                {"input": {"s": ".,"}, "expectedOutput": True}
            ]
        },
        {
            "id": "best-time-stock",
            "title": "Best Time to Buy and Sell Stock",
            "description": "You are given an integer array prices where prices[i] is the price of NeetCoin on the ith day. Choose one day to buy and a later day to sell. Return the maximum profit. If no profit is possible, return 0.",
            "difficulty": "Easy",
            "examples": [
                {
                    "input": "prices = [10,1,5,6,7,1]",
                    "output": "6",
                    "explanation": "Buy on day 2 (price 1) and sell on day 5 (price 7)."
                },
                {"input": "prices = [10,8,7,5,2]", "output": "0"}
            ],
            "constraints": [
                "1 <= prices.length <= 100",
                "0 <= prices[i] <= 100"
            ],
            "sampleTestCases": [
                {"input": {"prices": [10, 1, 5, 6, 7, 1]}, "expectedOutput": 6},
                {"input": {"prices": [10, 8, 7, 5, 2]}, "expectedOutput": 0}
            ],
            "hiddenTestCases": [
                {"input": {"prices": [1, 2]}, "expectedOutput": 1},
                {"input": {"prices": [3, 3, 3]}, "expectedOutput": 0},
                {"input": {"prices": [2, 1, 2, 1, 0, 1, 2]}, "expectedOutput": 2},
                {"input": {"prices": [1]}, "expectedOutput": 0},
                {"input": {"prices": [7, 1, 5, 3, 6, 4]}, "expectedOutput": 5},
                {"input": {"prices": [2, 4, 1]}, "expectedOutput": 2},
                {"input": {"prices": [3, 2, 6, 5, 0, 3]}, "expectedOutput": 4},
                {"input": {"prices": [1, 2, 3, 4, 5]}, "expectedOutput": 4},
                {"input": {"prices": [5, 4, 3, 2, 1]}, "expectedOutput": 0},
                {"input": {"prices": [100, 50, 75, 25, 100]}, "expectedOutput": 75},
                {"input": {"prices": [10, 5, 15, 20]}, "expectedOutput": 15}
            ]
        },
        {
            "id": "valid-parentheses",
            "title": "Valid Parentheses",
            "description": "You are given a string s consisting of the following characters: '(', ')', '{', '}', '[' and ']'. Return true if the input string is valid, and false otherwise.",
            "difficulty": "Easy",
            "examples": [
                {"input": "s = \"[]\"", "output": "true"},
                {"input": "s = \"([{}])\"", "output": "true"},
                {"input": "s = \"[(])\"", "output": "false"}
            ],
            "constraints": [
                "1 <= s.length <= 1000"
            ],
            "sampleTestCases": [
                {"input": {"s": "[]"}, "expectedOutput": True},
                {"input": {"s": "([{}])"}, "expectedOutput": True},
                {"input": {"s": "[(])"}, "expectedOutput": False}
            ],
            "hiddenTestCases": [
                {"input": {"s": "{[]}"}, "expectedOutput": True},
                {"input": {"s": "([)]"}, "expectedOutput": False},
                {"input": {"s": "((()))"}, "expectedOutput": True},
                {"input": {"s": "())"}, "expectedOutput": False},
                {"input": {"s": "((("}, "expectedOutput": False},
                {"input": {"s": "()[]{}"}, "expectedOutput": True},
                {"input": {"s": "{[()]}"}, "expectedOutput": True},
                {"input": {"s": "([{}])"}, "expectedOutput": True},
                {"input": {"s": "(]"}, "expectedOutput": False},
                {"input": {"s": "{{{"}, "expectedOutput": False},
                {"input": {"s": "(({{[[]]}})"}, "expectedOutput": False}
            ]
        },
        {
            "id": "reverse-linked-list",
            "title": "Reverse Linked List",
            "description": "Given the beginning of a singly linked list head, reverse the list, and return the new beginning of the list.",
            "difficulty": "Easy",
            "examples": [
                {"input": "head = [0,1,2,3]", "output": "[3,2,1,0]"},
                {"input": "head = []", "output": "[]"}
            ],
            "constraints": [
                "0 <= The length of the list <= 1000",
                "-1000 <= Node.val <= 1000"
            ],
            "sampleTestCases": [
                {"input": {"head": [0, 1, 2, 3]}, "expectedOutput": [3, 2, 1, 0]},
                {"input": {"head": []}, "expectedOutput": []}
            ],
            "hiddenTestCases": [
                {"input": {"head": [1]}, "expectedOutput": [1]},
                {"input": {"head": [1, 2]}, "expectedOutput": [2, 1]},
                {"input": {"head": [1, 2, 3]}, "expectedOutput": [3, 2, 1]},
                {"input": {"head": [1, 2, 3, 4, 5]}, "expectedOutput": [5, 4, 3, 2, 1]},
                {"input": {"head": [5, 4, 3, 2, 1]}, "expectedOutput": [1, 2, 3, 4, 5]},
                {"input": {"head": [10, 20]}, "expectedOutput": [20, 10]},
                {"input": {"head": [7]}, "expectedOutput": [7]},
                {"input": {"head": [-1, -2, -3]}, "expectedOutput": [-3, -2, -1]},
                {"input": {"head": [100, 200, 300, 400]}, "expectedOutput": [400, 300, 200, 100]},
                {"input": {"head": [1, 1, 1, 1]}, "expectedOutput": [1, 1, 1, 1]},
                {"input": {"head": [9, 8, 7, 6, 5, 4, 3, 2, 1]}, "expectedOutput": [1, 2, 3, 4, 5, 6, 7, 8, 9]}
            ]
        },
        {
            "id": "linked-list-cycle",
            "title": "Linked List Cycle Detection",
            "description": "Given the beginning of a linked list head, return true if there is a cycle in the linked list. Internally, an index determines where the tail connects; the index is not provided to your function.",
            "difficulty": "Easy",
            "examples": [
                {"input": "head = [1,2,3,4], index = 1", "output": "true"},
                {"input": "head = [1,2], index = -1", "output": "false"}
            ],
            "constraints": [
                "1 <= Length of the list <= 1000",
                "-1000 <= Node.val <= 1000"
            ],
            "sampleTestCases": [
                {"input": {"head": [1, 2, 3, 4], "pos": 1}, "expectedOutput": True},
                {"input": {"head": [1, 2], "pos": -1}, "expectedOutput": False}
            ],
            "hiddenTestCases": [
                {"input": {"head": [1], "pos": -1}, "expectedOutput": False},
                {"input": {"head": [1], "pos": 0}, "expectedOutput": True},
                {"input": {"head": [1, 2, 3], "pos": 2}, "expectedOutput": True},
                {"input": {"head": [1, 2, 3], "pos": 0}, "expectedOutput": True},
                {"input": {"head": [1, 2, 3, 4, 5], "pos": 2}, "expectedOutput": True},
                {"input": {"head": [1, 2, 3, 4], "pos": -1}, "expectedOutput": False},
                {"input": {"head": [1, 2, 3, 4, 5, 6], "pos": 3}, "expectedOutput": True},
                {"input": {"head": [10, 20, 30], "pos": -1}, "expectedOutput": False}
            ]
        }
    ],
    "medium": [
        {
            "id": "longest-consecutive",
            "title": "Longest Consecutive Sequence",
            "description": "Given an array of integers nums, return the length of the longest consecutive sequence of elements that can be formed. A consecutive sequence is a sequence where each element is exactly 1 greater than the previous element. You must write an algorithm that runs in O(n) time.",
            "difficulty": "Medium",
            "examples": [
                {"input": "nums = [2,20,4,10,3,4,5]", "output": "4", "explanation": "The longest consecutive sequence is [2,3,4,5]."},
                {"input": "nums = [0,3,2,5,4,6,1,1]", "output": "7"}
            ],
            "constraints": [
                "0 <= nums.length <= 1000",
                "-10^9 <= nums[i] <= 10^9"
            ],
            "sampleTestCases": [
                {"input": {"nums": [2, 20, 4, 10, 3, 4, 5]}, "expectedOutput": 4},
                {"input": {"nums": [0, 3, 2, 5, 4, 6, 1, 1]}, "expectedOutput": 7}
            ],
            "hiddenTestCases": [
                {"input": {"nums": []}, "expectedOutput": 0},
                {"input": {"nums": [100]}, "expectedOutput": 1},
                {"input": {"nums": [1, 2, 0, 1]}, "expectedOutput": 3},
                {"input": {"nums": [-1, -2, -3, 7, 8]}, "expectedOutput": 3},
                {"input": {"nums": [9, 1, 4, 7, 3, 2, 8, 5, 6]}, "expectedOutput": 9},
                {"input": {"nums": [100, 4, 200, 1, 3, 2]}, "expectedOutput": 4},
                {"input": {"nums": [0, -1, 1, 2, -2, -3]}, "expectedOutput": 6},
                {"input": {"nums": [1, 1, 1, 1]}, "expectedOutput": 1},
                {"input": {"nums": [10, 5, 12, 3, 55, 30, 4, 11, 2]}, "expectedOutput": 4},
                {"input": {"nums": [-5, -4, -3, -2, -1]}, "expectedOutput": 5},
                {"input": {"nums": [1000000000, 999999999, 1000000001]}, "expectedOutput": 3}
            ]
        },
        {
            "id": "three-sum",
            "title": "3Sum",
            "description": "Given an integer array nums, return all the triplets [nums[i], nums[j], nums[k]] where nums[i] + nums[j] + nums[k] == 0, and the indices i, j and k are all distinct. The output should not contain any duplicate triplets.",
            "difficulty": "Medium",
            "examples": [
                {"input": "nums = [-1,0,1,2,-1,-4]", "output": "[[-1,-1,2],[-1,0,1]]"},
                {"input": "nums = [0,1,1]", "output": "[]"},
                {"input": "nums = [0,0,0]", "output": "[[0,0,0]]"}
            ],
            "constraints": [
                "3 <= nums.length <= 1000",
                "-10^5 <= nums[i] <= 10^5"
            ],
            "sampleTestCases": [
                {"input": {"nums": [-1, 0, 1, 2, -1, -4]}, "expectedOutput": [[-1, -1, 2], [-1, 0, 1]]},
                {"input": {"nums": [0, 1, 1]}, "expectedOutput": []},
                {"input": {"nums": [0, 0, 0]}, "expectedOutput": [[0, 0, 0]]}
            ],
            "hiddenTestCases": [
                {"input": {"nums": [-2, 0, 0, 2, 2]}, "expectedOutput": [[-2, 0, 2]]},
                {"input": {"nums": [3, -2, 1, 0]}, "expectedOutput": []},
                {"input": {"nums": [-4, -2, -2, -2, 0, 1, 2, 2, 2, 4]}, "expectedOutput": [[-4, 0, 4], [-4, 2, 2], [-2, -2, 4], [-2, 0, 2]]},
                {"input": {"nums": [0, 0, 0, 0]}, "expectedOutput": [[0, 0, 0]]},
                {"input": {"nums": [-4, -1, -1, 0, 1, 2]}, "expectedOutput": [[-1, -1, 2], [-1, 0, 1]]},
                {"input": {"nums": [-2, 0, 1, 1, 2]}, "expectedOutput": [[-2, 0, 2], [-2, 1, 1]]},
                {"input": {"nums": [1, -1, 0, 2, -2, 3]}, "expectedOutput": [[-2, -1, 3], [-2, 0, 2], [-1, 0, 1]]},
                {"input": {"nums": [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5]}, "expectedOutput": [[-5, 0, 5], [-5, 1, 4], [-5, 2, 3], [-4, -1, 5], [-4, 0, 4], [-4, 1, 3], [-3, -2, 5], [-3, -1, 4], [-3, 0, 3], [-3, 1, 2], [-2, -1, 3], [-2, 0, 2], [-1, 0, 1]]},
                {"input": {"nums": [3, 0, -2, -1, 1, 2]}, "expectedOutput": [[-2, -1, 3], [-2, 0, 2], [-1, 0, 1]]},
                {"input": {"nums": [-1, 0, 1, 0]}, "expectedOutput": [[-1, 0, 1]]},
                {"input": {"nums": [1, 1, -2]}, "expectedOutput": [[-2, 1, 1]]}
            ]
        },
        {
            "id": "container-with-most-water",
            "title": "Container With Most Water",
            "description": "You are given an integer array heights where heights[i] represents the height of the ith bar. You may choose any two bars to form a container. Return the maximum amount of water a container can store.",
            "difficulty": "Medium",
            "examples": [
                {"input": "height = [1,7,2,5,4,7,3,6]", "output": "36"},
                {"input": "height = [2,2,2]", "output": "4"}
            ],
            "constraints": [
                "2 <= height.length <= 1000",
                "0 <= height[i] <= 1000"
            ],
            "sampleTestCases": [
                {"input": {"heights": [1, 7, 2, 5, 4, 7, 3, 6]}, "expectedOutput": 36},
                {"input": {"heights": [2, 2, 2]}, "expectedOutput": 4}
            ],
            "hiddenTestCases": [
                {"input": {"heights": [1, 1]}, "expectedOutput": 1},
                {"input": {"heights": [4, 3, 2, 1, 4]}, "expectedOutput": 16},
                {"input": {"heights": [1, 2, 1]}, "expectedOutput": 2},
                {"input": {"heights": [2, 3, 10, 5, 7, 8, 9]}, "expectedOutput": 36},
                {"input": {"heights": [1, 8, 6, 2, 5, 4, 8, 3, 7]}, "expectedOutput": 49},
                {"input": {"heights": [1, 1, 1, 1, 1]}, "expectedOutput": 4},
                {"input": {"heights": [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]}, "expectedOutput": 25},
                {"input": {"heights": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}, "expectedOutput": 25},
                {"input": {"heights": [100, 1, 1, 1, 1, 1, 100]}, "expectedOutput": 600},
                {"input": {"heights": [5, 2, 12, 1, 5, 3, 4, 11, 9, 4]}, "expectedOutput": 55},
                {"input": {"heights": [1, 3, 2, 5, 25, 24, 5]}, "expectedOutput": 24}
            ]
        },
        {
            "id": "find-min-rotated",
            "title": "Find Minimum in Rotated Sorted Array",
            "description": "You are given an array nums which was originally sorted in ascending order and then rotated. Assuming all elements are unique, return the minimum element. Write an algorithm that runs in O(log n) time.",
            "difficulty": "Medium",
            "examples": [
                {"input": "nums = [3,4,5,6,1,2]", "output": "1"},
                {"input": "nums = [4,5,0,1,2,3]", "output": "0"},
                {"input": "nums = [4,5,6,7]", "output": "4"}
            ],
            "constraints": [
                "1 <= nums.length <= 1000",
                "-1000 <= nums[i] <= 1000"
            ],
            "sampleTestCases": [
                {"input": {"nums": [3, 4, 5, 6, 1, 2]}, "expectedOutput": 1},
                {"input": {"nums": [4, 5, 0, 1, 2, 3]}, "expectedOutput": 0},
                {"input": {"nums": [4, 5, 6, 7]}, "expectedOutput": 4}
            ],
            "hiddenTestCases": [
                {"input": {"nums": [1]}, "expectedOutput": 1},
                {"input": {"nums": [2, 1]}, "expectedOutput": 1},
                {"input": {"nums": [5, 6, 7, 1, 2, 3, 4]}, "expectedOutput": 1},
                {"input": {"nums": [11, 13, 15, 17]}, "expectedOutput": 11},
                {"input": {"nums": [3, 1, 2]}, "expectedOutput": 1},
                {"input": {"nums": [4, 5, 6, 7, 0, 1, 2]}, "expectedOutput": 0},
                {"input": {"nums": [5, 1, 2, 3, 4]}, "expectedOutput": 1},
                {"input": {"nums": [10, 20, 30, 40, 50, 1, 2, 3]}, "expectedOutput": 1},
                {"input": {"nums": [2, 3, 4, 5, 1]}, "expectedOutput": 1},
                {"input": {"nums": [100, 200, 300, 1, 10, 20]}, "expectedOutput": 1},
                {"input": {"nums": [7, 8, 9, 10, 1, 2, 3, 4, 5, 6]}, "expectedOutput": 1}
            ]
        },
        {
            "id": "reorder-list",
            "title": "Reorder Linked List",
            "description": "Given the head of a singly linked-list, reorder the nodes to follow the pattern [0, n-1, 1, n-2, 2, n-3, ...]. You may not modify node values, only pointers.",
            "difficulty": "Medium",
            "examples": [
                {"input": "head = [2,4,6,8]", "output": "[2,8,4,6]"},
                {"input": "head = [2,4,6,8,10]", "output": "[2,10,4,8,6]"}
            ],
            "constraints": [
                "1 <= Length of the list <= 1000",
                "1 <= Node.val <= 1000"
            ],
            "sampleTestCases": [
                {"input": {"head": [2, 4, 6, 8]}, "expectedOutput": [2, 8, 4, 6]},
                {"input": {"head": [2, 4, 6, 8, 10]}, "expectedOutput": [2, 10, 4, 8, 6]}
            ],
            "hiddenTestCases": [
                {"input": {"head": [1]}, "expectedOutput": [1]},
                {"input": {"head": [1, 2]}, "expectedOutput": [1, 2]},
                {"input": {"head": [1, 2, 3]}, "expectedOutput": [1, 3, 2]},
                {"input": {"head": [1, 2, 3, 4, 5, 6]}, "expectedOutput": [1, 6, 2, 5, 3, 4]},
                {"input": {"head": [1, 2, 3, 4, 5, 6, 7]}, "expectedOutput": [1, 7, 2, 6, 3, 5, 4]},
                {"input": {"head": [1, 2, 3, 4, 5, 6, 7, 8]}, "expectedOutput": [1, 8, 2, 7, 3, 6, 4, 5]},
                {"input": {"head": [10, 20, 30, 40, 50]}, "expectedOutput": [10, 50, 20, 40, 30]},
                {"input": {"head": [5, 4, 3, 2, 1]}, "expectedOutput": [5, 1, 4, 2, 3]},
                {"input": {"head": [1, 2, 3, 4, 5, 6, 7, 8, 9]}, "expectedOutput": [1, 9, 2, 8, 3, 7, 4, 6, 5]},
                {"input": {"head": [100, 200]}, "expectedOutput": [100, 200]},
                {"input": {"head": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}, "expectedOutput": [1, 10, 2, 9, 3, 8, 4, 7, 5, 6]}
            ]
        },
        {
            "id": "group-anagrams",
            "title": "Group Anagrams",
            "description": "Given an array of strings strs, group all anagrams together into sublists. You may return the output in any order.",
            "difficulty": "Medium",
            "examples": [
                {
                    "input": "strs = [\"act\",\"pots\",\"tops\",\"cat\",\"stop\",\"hat\"]",
                    "output": "[[\"hat\"],[\"act\",\"cat\"],[\"stop\",\"pots\",\"tops\"]]"
                },
                {"input": "strs = [\"x\"]", "output": "[[\"x\"]]"},
                {"input": "strs = [\"\"]", "output": "[[\"\"]]"}
            ],
            "constraints": [
                "1 <= strs.length <= 1000",
                "0 <= strs[i].length <= 100",
                "strs[i] is made up of lowercase English letters"
            ],
            "sampleTestCases": [
                {
                    "input": {"strs": ["act", "pots", "tops", "cat", "stop", "hat"]},
                    "expectedOutput": [["hat"], ["act", "cat"], ["stop", "pots", "tops"]]
                },
                {"input": {"strs": ["x"]}, "expectedOutput": [["x"]]},
                {"input": {"strs": [""]}, "expectedOutput": [[""]]}
            ],
            "hiddenTestCases": [
                {"input": {"strs": []}, "expectedOutput": []},
                {"input": {"strs": ["ab", "ba", "abc", "bca", "cab"]}, "expectedOutput": [["ab", "ba"], ["abc", "bca", "cab"]]},
                {"input": {"strs": ["aa", "aa", "a"]}, "expectedOutput": [["aa", "aa"], ["a"]]},
                {"input": {"strs": ["abc", "bca", "cab", "xyz", "zyx", "yxz"]}, "expectedOutput": [["abc", "bca", "cab"], ["xyz", "zyx", "yxz"]]},
                {"input": {"strs": ["listen", "silent", "enlist", "hello", "world"]}, "expectedOutput": [["listen", "silent", "enlist"], ["hello"], ["world"]]},
                {"input": {"strs": ["a", "b", "c", "d"]}, "expectedOutput": [["a"], ["b"], ["c"], ["d"]]},
                {"input": {"strs": ["aa", "aa", "aa"]}, "expectedOutput": [["aa", "aa", "aa"]]},
                {"input": {"strs": ["dog", "god", "cat", "tac", "act"]}, "expectedOutput": [["dog", "god"], ["cat", "tac", "act"]]},
                {"input": {"strs": ["race", "care", "acre", "moon", "noon"]}, "expectedOutput": [["race", "care", "acre"], ["moon"], ["noon"]]},
                {"input": {"strs": ["stop", "pots", "tops", "spot", "opts"]}, "expectedOutput": [["stop", "pots", "tops", "spot", "opts"]]},
                {"input": {"strs": ["debit card", "bad credit"]}, "expectedOutput": [["debit card"], ["bad credit"]]}
            ]
        },
        {
            "id": "top-k-frequent",
            "title": "Top K Frequent Elements",
            "description": "Given an integer array nums and an integer k, return the k most frequent elements within the array. The answer is always unique. You may return the output in any order.",
            "difficulty": "Medium",
            "examples": [
                {"input": "nums = [1,2,2,3,3,3], k = 2", "output": "[2,3]"},
                {"input": "nums = [7,7], k = 1", "output": "[7]"}
            ],
            "constraints": [
                "1 <= nums.length <= 10^4",
                "-1000 <= nums[i] <= 1000",
                "1 <= k <= number of distinct elements in nums",
                "The answer is always unique"
            ],
            "sampleTestCases": [
                {"input": {"nums": [1, 2, 2, 3, 3, 3], "k": 2}, "expectedOutput": [2, 3]},
                {"input": {"nums": [7, 7], "k": 1}, "expectedOutput": [7]}
            ],
            "hiddenTestCases": [
                {"input": {"nums": [1], "k": 1}, "expectedOutput": [1]},
                {"input": {"nums": [4, 4, 4, 5, 5, 6], "k": 2}, "expectedOutput": [4, 5]},
                {"input": {"nums": [-1, -1, -2, -2, -2, 3], "k": 2}, "expectedOutput": [-2, -1]},
                {"input": {"nums": [1, 1, 1, 2, 2, 3], "k": 2}, "expectedOutput": [1, 2]},
                {"input": {"nums": [5, 5, 5, 5, 1, 1, 1, 2, 2, 3], "k": 3}, "expectedOutput": [5, 1, 2]},
                {"input": {"nums": [100, 100, 100, 200, 200, 300], "k": 1}, "expectedOutput": [100]},
                {"input": {"nums": [7, 7, 8, 8, 9, 9], "k": 3}, "expectedOutput": [7, 8, 9]},
                {"input": {"nums": [0, 0, 0, -1, -1, -2], "k": 2}, "expectedOutput": [0, -1]},
                {"input": {"nums": [10, 10, 20, 20, 30, 30, 40], "k": 3}, "expectedOutput": [10, 20, 30]},
                {"input": {"nums": [1, 2, 3, 4, 5, 5, 5, 5], "k": 1}, "expectedOutput": [5]},
                {"input": {"nums": [3, 3, 3, 2, 2, 1], "k": 2}, "expectedOutput": [3, 2]}
            ]
        },
        {
            "id": "palindrome-number",
            "title": "Palindrome Number",
            "description": "Given an integer x, return true if x is a palindrome, and false otherwise.",
            "difficulty": "Medium",
            "examples": [
                {"input": "x = 121", "output": "true", "explanation": "121 reads as 121 from left to right and from right to left."}
            ],
            "constraints": [
                "-2^31 <= x <= 2^31 - 1"
            ],
            "sampleTestCases": [
                {"input": {"x": 121}, "expectedOutput": True},
                {"input": {"x": -121}, "expectedOutput": False},
                {"input": {"x": 10}, "expectedOutput": False}
            ],
            "hiddenTestCases": [
                {"input": {"x": 0}, "expectedOutput": True},
                {"input": {"x": 1}, "expectedOutput": True},
                {"input": {"x": 12321}, "expectedOutput": True},
                {"input": {"x": 123}, "expectedOutput": False},
                {"input": {"x": -101}, "expectedOutput": False},
                {"input": {"x": 1000021}, "expectedOutput": False},
                {"input": {"x": 9}, "expectedOutput": True},
                {"input": {"x": 1001}, "expectedOutput": True},
                {"input": {"x": 12345}, "expectedOutput": False},
                {"input": {"x": 99}, "expectedOutput": True},
                {"input": {"x": 1234321}, "expectedOutput": True}
            ]
        }
    ],
    "hard": [
        {
            "id": "minimum-window-substring",
            "title": "Minimum Window Substring",
            "description": "Given two strings s and t, return the shortest substring of s such that every character in t (including duplicates) is present. If no such substring exists, return an empty string. You may assume the correct output is always unique.",
            "difficulty": "Hard",
            "examples": [
                {"input": "s = \"OUZODYXAZV\", t = \"XYZ\"", "output": "\"YXAZ\""},
                {"input": "s = \"xyz\", t = \"xyz\"", "output": "\"xyz\""},
                {"input": "s = \"x\", t = \"xy\"", "output": "\"\""}
            ],
            "constraints": [
                "1 <= s.length <= 1000",
                "1 <= t.length <= 1000",
                "s and t consist of uppercase and lowercase English letters"
            ],
            "sampleTestCases": [
                {"input": {"s": "OUZODYXAZV", "t": "XYZ"}, "expectedOutput": "YXAZ"},
                {"input": {"s": "xyz", "t": "xyz"}, "expectedOutput": "xyz"},
                {"input": {"s": "x", "t": "xy"}, "expectedOutput": ""}
            ],
            "hiddenTestCases": [
                {"input": {"s": "ADOBECODEBANC", "t": "ABC"}, "expectedOutput": "BANC"},
                {"input": {"s": "aa", "t": "aa"}, "expectedOutput": "aa"},
                {"input": {"s": "a", "t": "a"}, "expectedOutput": "a"},
                {"input": {"s": "a", "t": "aa"}, "expectedOutput": ""},
                {"input": {"s": "ab", "t": "b"}, "expectedOutput": "b"},
                {"input": {"s": "abc", "t": "cba"}, "expectedOutput": "abc"},
                {"input": {"s": "ADOBECODEBANCAAA", "t": "AAA"}, "expectedOutput": "AAA"},
                {"input": {"s": "cabwefgewcwaefgcf", "t": "cae"}, "expectedOutput": "cwae"},
                {"input": {"s": "bba", "t": "ab"}, "expectedOutput": "ba"},
                {"input": {"s": "aaaaaaaaaaaabbbbbcdd", "t": "abcdd"}, "expectedOutput": "abbbbbcdd"},
                {"input": {"s": "bdab", "t": "ab"}, "expectedOutput": "ab"}
            ]
        },
        {
            "id": "longest-substring",
            "title": "Longest Substring Without Repeating Characters",
            "description": "Given a string s, find the length of the longest substring without repeating characters.",
            "difficulty": "Hard",
            "examples": [
                {"input": "s = \"abcabcbb\"", "output": "3", "explanation": "The answer is \"abc\", with the length of 3."}
            ],
            "constraints": [
                "0 <= s.length <= 5 * 10^4",
                "s consists of English letters, digits, symbols and spaces"
            ],
            "sampleTestCases": [
                {"input": {"s": "abcabcbb"}, "expectedOutput": 3},
                {"input": {"s": "bbbbb"}, "expectedOutput": 1},
                {"input": {"s": "pwwkew"}, "expectedOutput": 3}
            ],
            "hiddenTestCases": [
                {"input": {"s": ""}, "expectedOutput": 0},
                {"input": {"s": " "}, "expectedOutput": 1},
                {"input": {"s": "au"}, "expectedOutput": 2},
                {"input": {"s": "dvdf"}, "expectedOutput": 3},
                {"input": {"s": "anviaj"}, "expectedOutput": 5},
                {"input": {"s": "abcdefg"}, "expectedOutput": 7},
                {"input": {"s": "tmmzuxt"}, "expectedOutput": 5},
                {"input": {"s": "abba"}, "expectedOutput": 2},
                {"input": {"s": "aab"}, "expectedOutput": 2},
                {"input": {"s": "cdd"}, "expectedOutput": 2},
                {"input": {"s": "abcabcbb"}, "expectedOutput": 3}
            ]
        },
        {
            "id": "merge-intervals",
            "title": "Merge Intervals",
            "description": "Given an array of intervals where intervals[i] = [starti, endi], merge all overlapping intervals, and return an array of the non-overlapping intervals that cover all the intervals in the input.",
            "difficulty": "Hard",
            "examples": [
                {"input": "intervals = [[1,3],[2,6],[8,10],[15,18]]", "output": "[[1,6],[8,10],[15,18]]", "explanation": "Since intervals [1,3] and [2,6] overlap, merge them into [1,6]."}
            ],
            "constraints": [
                "1 <= intervals.length <= 10^4",
                "intervals[i].length == 2",
                "0 <= starti <= endi <= 10^4"
            ],
            "sampleTestCases": [
                {"input": {"intervals": [[1,3],[2,6],[8,10],[15,18]]}, "expectedOutput": [[1,6],[8,10],[15,18]]},
                {"input": {"intervals": [[1,4],[4,5]]}, "expectedOutput": [[1,5]]}
            ],
            "hiddenTestCases": [
                {"input": {"intervals": [[1,3]]}, "expectedOutput": [[1,3]]},
                {"input": {"intervals": [[1,4],[0,4]]}, "expectedOutput": [[0,4]]},
                {"input": {"intervals": [[1,4],[0,1]]}, "expectedOutput": [[0,4]]},
                {"input": {"intervals": [[1,4],[2,3]]}, "expectedOutput": [[1,4]]},
                {"input": {"intervals": [[1,4],[0,0],[5,5]]}, "expectedOutput": [[0,0],[1,4],[5,5]]},
                {"input": {"intervals": [[2,3],[4,5],[6,7],[8,9],[1,10]]}, "expectedOutput": [[1,10]]},
                {"input": {"intervals": [[1,4],[0,2],[3,5]]}, "expectedOutput": [[0,5]]},
                {"input": {"intervals": [[1,10],[2,3],[4,5],[6,7]]}, "expectedOutput": [[1,10]]},
                {"input": {"intervals": [[1,2],[3,4],[5,6],[7,8]]}, "expectedOutput": [[1,2],[3,4],[5,6],[7,8]]},
                {"input": {"intervals": [[0,0],[1,2],[5,5],[2,4],[3,3]]}, "expectedOutput": [[0,0],[1,4],[5,5]]},
                {"input": {"intervals": [[2,6],[1,3],[8,10],[15,18]]}, "expectedOutput": [[1,6],[8,10],[15,18]]}
            ]
        },
        {
            "id": "merge-k-sorted-lists",
            "title": "Merge K Sorted Linked Lists",
            "description": "You are given an array of k linked lists lists, where each list is sorted in ascending order. Return the sorted linked list that is the result of merging all lists.",
            "difficulty": "Hard",
            "examples": [
                {"input": "lists = [[1,2,4],[1,3,5],[3,6]]", "output": "[1,1,2,3,3,4,5,6]"},
                {"input": "lists = []", "output": "[]"},
                {"input": "lists = [[]]", "output": "[]"}
            ],
            "constraints": [
                "0 <= lists.length <= 1000",
                "0 <= lists[i].length <= 100",
                "-1000 <= lists[i][j] <= 1000"
            ],
            "sampleTestCases": [
                {"input": {"lists": [[1, 2, 4], [1, 3, 5], [3, 6]]}, "expectedOutput": [1, 1, 2, 3, 3, 4, 5, 6]},
                {"input": {"lists": []}, "expectedOutput": []},
                {"input": {"lists": [[]]}, "expectedOutput": []}
            ],
            "hiddenTestCases": [
                {"input": {"lists": [[1], [0]]}, "expectedOutput": [0, 1]},
                {"input": {"lists": [[-1, 5, 11], [6, 10]]}, "expectedOutput": [-1, 5, 6, 10, 11]},
                {"input": {"lists": [[], [2], [], [1, 3]]}, "expectedOutput": [1, 2, 3]},
                {"input": {"lists": [[1, 4, 5], [1, 3, 4], [2, 6]]}, "expectedOutput": [1, 1, 2, 3, 4, 4, 5, 6]},
                {"input": {"lists": [[-10, -9, -9, -3, -1], [-5]]}, "expectedOutput": [-10, -9, -9, -5, -3, -1]},
                {"input": {"lists": [[1], [1], [1]]}, "expectedOutput": [1, 1, 1]},
                {"input": {"lists": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}, "expectedOutput": [1, 2, 3, 4, 5, 6, 7, 8, 9]},
                {"input": {"lists": [[-2, -1, 0], [1, 2, 3]]}, "expectedOutput": [-2, -1, 0, 1, 2, 3]},
                {"input": {"lists": [[100, 200], [50, 150], [25, 75, 125]]}, "expectedOutput": [25, 50, 75, 100, 125, 150, 200]},
                {"input": {"lists": [[5], [3], [1], [7], [9]]}, "expectedOutput": [1, 3, 5, 7, 9]},
                {"input": {"lists": [[0, 1, 2], [0, 1, 2], [0, 1, 2]]}, "expectedOutput": [0, 0, 0, 1, 1, 1, 2, 2, 2]}
            ]
        }
    ]
}

# In-memory per-client pools so question selection doesn't keep repeating.
# Note: This is best-effort for local/dev. In production you'd back this by Redis/DB.
_TECHNICAL_QUESTION_POOLS: dict[str, dict[str, list[str]]] = {}


def _draw_questions_no_repeat(
    *,
    client_id: Optional[str],
    pool_key: str,
    candidates: list[dict],
    count: int,
) -> list[dict]:
    """Draw up to `count` questions from `candidates` without replacement for this client."""
    if count <= 0:
        return []
    if not candidates:
        return []

    if not client_id:
        # Backward-compatible behavior if no client is provided.
        import random
        return random.sample(candidates, min(count, len(candidates)))

    import random

    candidate_by_id = {q.get("id"): q for q in candidates if q.get("id")}
    candidate_ids = [qid for qid in candidate_by_id.keys()]
    if not candidate_ids:
        return []

    client_pools = _TECHNICAL_QUESTION_POOLS.setdefault(client_id, {})
    pool = client_pools.get(pool_key)

    # Reset pool if missing or if the candidate set changed.
    if not pool or set(pool) != set(candidate_ids):
        pool = candidate_ids[:]
        random.shuffle(pool)

    picked: list[dict] = []
    # Draw without replacement; if pool runs out, reshuffle remaining candidates.
    while len(picked) < min(count, len(candidate_ids)):
        if not pool:
            pool = candidate_ids[:]
            random.shuffle(pool)
        qid = pool.pop()
        q = candidate_by_id.get(qid)
        if q:
            picked.append(q)

    client_pools[pool_key] = pool
    return picked


class TechnicalQuestionsRequest(BaseModel):
    company: str
    role: str
    difficulty: str
    client_id: Optional[str] = None

class RunCodeRequest(BaseModel):
    code: str
    question_id: str
    language: str = "python"  # python, javascript, java, cpp, c
    run_mode: str = "run"  # "run" for sample tests, "submit" for all tests


class GenerateTechnicalProblemRequest(BaseModel):
    question: dict
    client_id: Optional[str] = None


class GradeTechnicalProblemRequest(BaseModel):
    session_id: str
    code: str
    language: str = "python"  # python, javascript
    run_mode: str = "run"  # "run" for sample tests, "submit" for all tests

class VoiceInterviewRequest(BaseModel):
    company: str
    role: str

@app.post("/api/technical-questions")
async def get_technical_questions(request: TechnicalQuestionsRequest):
    """Get technical interview questions based on difficulty."""
    try:
        d = (request.difficulty or "easy").strip().lower()
        requested = d if d in {"easy", "medium", "hard"} else "easy"
        candidates = TECHNICAL_QUESTIONS.get(requested, [])

        selected_questions = _draw_questions_no_repeat(
            client_id=request.client_id,
            pool_key=f"hardcoded:{requested}:main",
            candidates=candidates,
            count=2,
        )

        return JSONResponse(
            content={
                "questions": selected_questions,
                "company": request.company,
                "role": request.role,
                "difficulty": request.difficulty,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


def execute_python_code(code: str, test_input: dict, function_name: str = "solution") -> tuple[any, str]:
    """Execute Python code and return result and error message."""
    try:
        # Create a safe execution environment
        from typing import Any, Dict, List, Optional

        class ListNode:
            def __init__(self, val: int = 0, next: Optional["ListNode"] = None):
                self.val = val
                self.next = next

        def _build_linked_list(values: List[int]) -> Optional[ListNode]:
            dummy = ListNode(0)
            cur = dummy
            for v in values:
                cur.next = ListNode(v)
                cur = cur.next
            return dummy.next

        def _linked_list_to_list(head: Optional[ListNode], limit: int = 5000) -> List[int]:
            out: List[int] = []
            cur = head
            steps = 0
            while cur is not None and steps < limit:
                out.append(cur.val)
                cur = cur.next
                steps += 1
            return out

        def _build_cycle(values: List[int], pos: int) -> Optional[ListNode]:
            head = _build_linked_list(values)
            if head is None or pos is None or pos < 0:
                return head
            # Find tail and pos node
            tail = head
            idx = 0
            pos_node = head if pos == 0 else None
            while tail.next is not None:
                tail = tail.next
                idx += 1
                if idx == pos:
                    pos_node = tail
            if pos_node is not None:
                tail.next = pos_node
            return head

        namespace = {
            "__builtins__": __builtins__,
            "ListNode": ListNode,
            "Optional": Optional,
            "List": List,
            "Any": Any,
            "Dict": Dict,
        }
        exec(code, namespace)
        
        # Try to find the solution function
        solution_func = None
        
        # First try: Look for Solution class with method (LeetCode pattern)
        if "Solution" in namespace:
            solution_class = namespace["Solution"]
            solution_instance = solution_class()
            if hasattr(solution_instance, function_name):
                solution_func = getattr(solution_instance, function_name)
        
        # Second try: Look for standalone function
        if solution_func is None and function_name in namespace:
            solution_func = namespace[function_name]
        
        # Third try: Look for any callable that's not a builtin
        if solution_func is None:
            for key, value in namespace.items():
                if callable(value) and not key.startswith("_") and key not in ["Solution", "print", "len", "range", "str", "int", "list", "dict", "set", "tuple"]:
                    solution_func = value
                    break
        
        if solution_func is None:
            return None, "No solution function found. Please define a class 'Solution' with a method matching the problem."
        
        # Execute with test input
        # Handle different input formats based on question type
        if "lists" in test_input:
            # Merge K Sorted Lists
            lists_in = test_input.get("lists") or []
            list_nodes: List[Optional[ListNode]] = []
            for arr in lists_in:
                if arr:
                    list_nodes.append(_build_linked_list(arr))
                else:
                    list_nodes.append(None)
            out_head = solution_func(list_nodes)
            if out_head is None:
                return [], None
            return _linked_list_to_list(out_head), None

        if "head" in test_input:
            head_vals = test_input.get("head") or []
            pos = test_input.get("pos")
            if isinstance(pos, int) and pos >= 0:
                head_node = _build_cycle(head_vals, pos)
            else:
                head_node = _build_linked_list(head_vals)

            # Reorder list modifies in place and returns None
            if function_name == "reorderList":
                solution_func(head_node)
                return _linked_list_to_list(head_node), None

            out = solution_func(head_node)
            if isinstance(out, ListNode) or out is None:
                return _linked_list_to_list(out), None
            return out, None

        if "nums" in test_input and "target" in test_input:
            # Two Sum problem
            nums_copy = test_input["nums"].copy() if isinstance(test_input["nums"], list) else test_input["nums"]
            result = solution_func(nums_copy, test_input["target"])
        elif "nums" in test_input and "k" in test_input:
            # Top K Frequent
            nums_copy = test_input["nums"].copy() if isinstance(test_input["nums"], list) else test_input["nums"]
            result = solution_func(nums_copy, test_input["k"])
        elif "s" in test_input and "t" in test_input:
            # Two-string problems (Valid Anagram)
            result = solution_func(test_input["s"], test_input["t"])
        elif "s" in test_input:
            # String problems - handle both string and list inputs
            s_input = test_input["s"]
            if isinstance(s_input, list):
                # For reverse string problem, modify in place
                s_copy = s_input.copy()  # Make a copy to avoid modifying original
                solution_func(s_copy)
                result = s_copy  # Function modifies in place, return the modified list
            else:
                result = solution_func(s_input)
        elif "intervals" in test_input:
            # Merge intervals - make a deep copy
            import copy
            intervals_copy = copy.deepcopy(test_input["intervals"])
            result = solution_func(intervals_copy)
        elif "root" in test_input:
            # Tree problems - skip for now
            return None, "Tree problems not yet supported"
        else:
            # Generic single argument
            input_val = list(test_input.values())[0]
            if isinstance(input_val, list):
                input_val = input_val.copy()
            result = solution_func(input_val)
        
        return result, None
    except Exception as e:
        import traceback
        error_msg = str(e)
        # Get more detailed error info but limit it
        tb = traceback.format_exc()
        # Only show the last few lines of traceback
        tb_lines = tb.split('\n')
        if len(tb_lines) > 5:
            error_msg = f"{error_msg}\n{tb_lines[-3]}"
        return None, error_msg


def execute_javascript_code(code: str, test_input: dict, function_name: str = "solution") -> tuple[any, str]:
    """Execute JavaScript code using Node.js subprocess."""
    import subprocess
    import json
    import tempfile
    
    try:
        # Create a test wrapper
        test_code = f"""
{code}

// Test execution
const testInput = {json.dumps(test_input)};
let result;
try {{
    const fn = (typeof {function_name} === 'function') ? {function_name} : ((typeof solution === 'function') ? solution : null);
    if (!fn) throw new Error('Solution function not found');

    if (testInput.nums !== undefined && testInput.target !== undefined) {{
        result = fn(testInput.nums, testInput.target);
    }} else if (testInput.nums !== undefined && testInput.k !== undefined) {{
        result = fn(testInput.nums, testInput.k);
    }} else if (testInput.s !== undefined && testInput.t !== undefined) {{
        result = fn(testInput.s, testInput.t);
    }} else if (testInput.s !== undefined) {{
        result = fn(testInput.s);
    }} else {{
        result = fn(Object.values(testInput)[0]);
    }}
    console.log(JSON.stringify({{result: result}}));
}} catch (error) {{
    console.error(JSON.stringify({{error: error.message}}));
    process.exit(1);
}}
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(test_code)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                ['node', temp_file],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                error_output = result.stderr
                try:
                    error_data = json.loads(error_output)
                    return None, error_data.get('error', error_output)
                except:
                    return None, error_output
            
            output_data = json.loads(result.stdout)
            return output_data.get('result'), None
        finally:
            os.unlink(temp_file)
    except subprocess.TimeoutExpired:
        return None, "Execution timeout"
    except Exception as e:
        return None, str(e)


def execute_python_code_generated(code: str, test_input: dict, function_name: str = "solution") -> tuple[Any, Optional[str]]:
    """Execute Python code for generated problems.

    Generated problems always call `solution(input)` with the entire input dict.
    """
    try:
        namespace = {"__builtins__": __builtins__}
        exec(code, namespace)

        solution_func = None

        if "Solution" in namespace:
            solution_class = namespace["Solution"]
            solution_instance = solution_class()
            if hasattr(solution_instance, function_name):
                solution_func = getattr(solution_instance, function_name)

        if solution_func is None and function_name in namespace:
            solution_func = namespace[function_name]

        if solution_func is None:
            for key, value in namespace.items():
                if callable(value) and not key.startswith("_") and key not in [
                    "Solution",
                    "print",
                    "len",
                    "range",
                    "str",
                    "int",
                    "list",
                    "dict",
                    "set",
                    "tuple",
                ]:
                    solution_func = value
                    break

        if solution_func is None:
            return None, "No solution function found. Please define `solution(input)` or `class Solution` with a `solution` method."

        result = solution_func(test_input)
        return result, None
    except Exception as e:
        import traceback

        error_msg = str(e)
        tb = traceback.format_exc()
        tb_lines = tb.split("\n")
        if len(tb_lines) > 5:
            error_msg = f"{error_msg}\n{tb_lines[-3]}"
        return None, error_msg


def execute_javascript_code_generated(code: str, test_input: dict, function_name: str = "solution") -> tuple[Any, Optional[str]]:
    """Execute JavaScript code for generated problems.

    Generated problems always call `solution(input)` with the entire input object.
    """
    import subprocess
    import json as _json
    import tempfile

    try:
        test_code = f"""
{code}

const testInput = {_json.dumps(test_input)};
let result;
try {{
  if (typeof {function_name} === 'function') {{
    result = {function_name}(testInput);
  }} else if (typeof solution === 'function') {{
    result = solution(testInput);
  }} else {{
    throw new Error('Solution function not found');
  }}
  console.log(JSON.stringify({{result: result}}));
}} catch (error) {{
  console.error(JSON.stringify({{error: error.message}}));
  process.exit(1);
}}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
            f.write(test_code)
            temp_file = f.name

        try:
            result = subprocess.run(
                ["node", temp_file],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                error_output = result.stderr
                try:
                    error_data = _json.loads(error_output)
                    return None, error_data.get("error", error_output)
                except Exception:
                    return None, error_output

            output_data = _json.loads(result.stdout)
            return output_data.get("result"), None
        finally:
            os.unlink(temp_file)
    except subprocess.TimeoutExpired:
        return None, "Execution timeout"
    except Exception as e:
        return None, str(e)


@app.post("/api/technical/problem")
async def generate_technical_problem(request: GenerateTechnicalProblemRequest):
    """Generate an original practice prompt + tests for a selected question metadata."""
    try:
        _prune_generated_technical_sessions()

        question = request.question or {}
        qid = str(question.get("id") or question.get("question_id") or "").strip()
        client_id = (request.client_id or "").strip() or "anon"
        index_key = f"{client_id}:{qid}" if qid else ""

        # If we already generated a session for this client + question, reuse it.
        if index_key and index_key in _generated_technical_session_index:
            existing_id = _generated_technical_session_index[index_key]
            sess = _generated_technical_sessions.get(existing_id)
            if sess:
                return JSONResponse(
                    content={
                        "session_id": existing_id,
                        "problem": sess["problem"],
                        "question": sess.get("question") or question,
                    }
                )

        try:
            problem = await _generate_original_problem_from_metadata(question)
        except Exception as e:
            print(f"[WARN] Problem generation failed, using fallback: {e}")
            problem = _validate_generated_problem_payload(_generate_problem_fallback(question))

        import uuid

        session_id = str(uuid.uuid4())
        _generated_technical_sessions[session_id] = {
            "created_at": time.time(),
            "question": question,
            "problem": problem,
        }
        if index_key:
            _generated_technical_session_index[index_key] = session_id

        return JSONResponse(content={"session_id": session_id, "problem": problem, "question": question})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate problem: {str(e)}")


async def analyze_time_complexity_with_ai(code: str, question_title: str, question_description: str, language: str) -> dict:
    """
    Use AI to analyze if the solution has optimal time complexity.
    Returns dict with 'is_optimal' (bool) and 'analysis' (str).
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""You are an expert algorithms instructor. Analyze the time complexity of this {language} solution.

Question: {question_title}
Description: {question_description}

Code:
```{language}
{code}
```

Determine if this solution uses the MOST EFFICIENT time complexity for this problem.

Respond in this EXACT JSON format:
{{
  "is_optimal": true or false,
  "actual_complexity": "O(...)",
  "optimal_complexity": "O(...)",
  "reasoning": "Brief explanation"
}}

Be strict - only mark as optimal if it uses the best known approach."""

        response = await call_gemini_with_retry_async(
            client=client,
            model="gemini-2.5-flash",
            contents=prompt,
            max_retries=2,
            initial_delay=1
        )

        # Parse JSON response
        response_text = response.text if hasattr(response, 'text') else str(response)
        result = _extract_first_json_object(response_text)

        return {
            "is_optimal": result.get("is_optimal", True),  # Default to optimal if parsing fails
            "actual_complexity": result.get("actual_complexity", "Unknown"),
            "optimal_complexity": result.get("optimal_complexity", "Unknown"),
            "reasoning": result.get("reasoning", "")
        }
    except Exception as e:
        print(f"Error analyzing time complexity with AI: {str(e)}")
        # Fallback: assume optimal if AI fails
        return {
            "is_optimal": True,
            "actual_complexity": "Unknown",
            "optimal_complexity": "Unknown",
            "reasoning": "AI analysis unavailable"
        }


def analyze_time_complexity(code: str, question_id: str, language: str) -> bool:
    """
    Analyze if the solution has optimal time complexity.
    Returns True if optimal, False otherwise.
    This is a simple pattern-based fallback.
    """
    # Define optimal complexity patterns for common questions
    optimal_patterns = {
        "two-sum": ["hash", "dict", "map", "set"],  # O(n) with hash map
        "contains-duplicate": ["set", "hash"],  # O(n) with set
        "valid-anagram": ["sorted", "counter", "hash", "dict"],  # O(n log n) or O(n)
        "best-time-stock": ["max"],  # O(n) single pass
        "valid-parentheses": ["stack", "append", "push", "pop"],  # O(n) with stack
        "longest-consecutive": ["set", "hash"],  # O(n) with set
        "three-sum": ["sort"],  # O(n²) with two pointers
        "container-with-most-water": ["two.*pointer", "left.*right"],  # O(n) two pointers
        "product-except-self": ["prefix", "suffix", "forward", "backward"],  # O(n) prefix/suffix
        "merge-intervals": ["sort"],  # O(n log n) with sorting
        "top-k-frequent": ["heap", "counter", "bucket"],  # O(n) or O(n log k)
        "group-anagrams": ["sort.*join", "sorted", "counter"],  # O(n * k log k)
    }

    # Suboptimal patterns that indicate inefficiency
    suboptimal_patterns = {
        "two-sum": ["for.*for", "nested.*loop"],  # O(n²) nested loops
        "contains-duplicate": ["for.*for"],  # O(n²) nested loops
        "longest-consecutive": ["for.*for"],  # O(n²) without set
        "product-except-self": ["division", "/"],  # Using division (technically works but not the intended solution)
    }

    code_lower = code.lower()

    # Check for suboptimal patterns first
    if question_id in suboptimal_patterns:
        import re
        for pattern in suboptimal_patterns[question_id]:
            if re.search(pattern, code_lower):
                return False

    # Check for optimal patterns
    if question_id in optimal_patterns:
        for pattern in optimal_patterns[question_id]:
            import re
            if re.search(pattern, code_lower):
                return True
        return False  # No optimal pattern found

    # For questions not in the list, assume optimal (no penalty)
    return True


@app.post("/api/technical/grade")
async def grade_technical_problem(request: GradeTechnicalProblemRequest):
    """Grade candidate code against a generated problem session."""
    try:
        sess = _generated_technical_sessions.get(request.session_id)
        if not sess:
            raise HTTPException(status_code=404, detail="Problem session not found (it may have expired).")

        problem = sess.get("problem") or {}
        run_mode = (request.run_mode or "run").strip().lower()
        if run_mode not in {"run", "submit"}:
            run_mode = "run"

        sample_tests = problem.get("sample_tests") or []
        hidden_tests = problem.get("hidden_tests") or []
        test_cases = sample_tests + hidden_tests if run_mode == "submit" else sample_tests

        test_results = []
        passed_count = 0
        total_tests = len(test_cases)

        for idx, test_case in enumerate(test_cases):
            test_input = test_case.get("input") or {}
            expected_output = test_case.get("expectedOutput")

            if request.language == "python":
                actual_output, error = execute_python_code_generated(request.code, test_input, "solution")
            elif request.language == "javascript":
                actual_output, error = execute_javascript_code_generated(request.code, test_input, "solution")
            else:
                return JSONResponse(
                    content={
                        "passed": False,
                        "score": 0,
                        "passed_tests": 0,
                        "total_tests": total_tests,
                        "test_results": [
                            {
                                "test_case": 1,
                                "input": test_input,
                                "expected_output": expected_output,
                                "actual_output": None,
                                "passed": False,
                                "error": "Only python and javascript are supported for autograding.",
                            }
                        ],
                    }
                )

            if error:
                passed = False
                actual_output = None
            else:
                passed = compare_outputs(actual_output, expected_output)

            test_results.append(
                {
                    "test_case": idx + 1,
                    "input": test_input,
                    "expected_output": expected_output,
                    "actual_output": actual_output,
                    "passed": passed,
                    "error": error,
                }
            )

            if passed:
                passed_count += 1

        score = (passed_count / total_tests) * 100 if total_tests > 0 else 0
        all_passed = passed_count == total_tests

        return JSONResponse(
            content={
                "passed": all_passed,
                "score": round(score, 1),
                "passed_tests": passed_count,
                "total_tests": total_tests,
                "test_results": test_results,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@app.post("/api/run-code")
async def run_code(request: RunCodeRequest):
    """Evaluate code against test cases with actual execution."""
    try:
        if request.language not in {"python", "javascript"}:
            raise HTTPException(
                status_code=400,
                detail="Autograding currently supports Python and JavaScript only.",
            )

        # Find the question
        question = None
        for diff_level in ["easy", "medium", "hard"]:
            for q in TECHNICAL_QUESTIONS.get(diff_level, []):
                if q["id"] == request.question_id:
                    question = q
                    break
            if question:
                break

        if not question:
            print(f"Question not found: {request.question_id}")
            raise HTTPException(status_code=404, detail=f"Question not found: {request.question_id}")

        linked_list_only_python = {
            "reverse-linked-list",
            "linked-list-cycle",
            "reorder-list",
            "merge-k-sorted-lists",
        }
        if request.language == "javascript" and question["id"] in linked_list_only_python:
            raise HTTPException(
                status_code=400,
                detail="Linked-list questions are currently autograded in Python only.",
            )
        
        # Determine which test cases to use based on run_mode
        if request.run_mode == "submit":
            # Use both sample and hidden test cases for submission
            test_cases = question.get("sampleTestCases", question.get("testCases", [])) + question.get("hiddenTestCases", [])
        else:
            # Only use sample test cases for "Run"
            test_cases = question.get("sampleTestCases", question.get("testCases", []))

        # Execute code against each test case
        test_results = []
        passed_count = 0
        total_tests = len(test_cases)

        print(f"Running code for question: {question['id']}, Mode: {request.run_mode}, Total tests: {total_tests}")

        # Determine function name based on question
        function_name_map = {
            "two-sum": "twoSum",
            "contains-duplicate": "hasDuplicate",
            "valid-anagram": "isAnagram",
            "valid-palindrome": "isPalindrome",
            "palindrome-number": "isPalindrome",
            "best-time-stock": "maxProfit",
            "fizz-buzz": "fizzBuzz",
            "longest-substring": "lengthOfLongestSubstring",
            "valid-parentheses": "isValid",
            "longest-consecutive": "longestConsecutive",
            "three-sum": "threeSum",
            "container-with-most-water": "maxArea",
            "find-min-rotated": "findMin",
            "group-anagrams": "groupAnagrams",
            "top-k-frequent": "topKFrequent",
            "minimum-window-substring": "minWindow",
            "product-except-self": "productExceptSelf",
            "merge-intervals": "merge",
            "reverse-linked-list": "reverseList",
            "linked-list-cycle": "hasCycle",
            "reorder-list": "reorderList",
            "merge-k-sorted-lists": "mergeKLists",
        }
        function_name = function_name_map.get(question["id"], "solution")

        print(f"Using function name: {function_name}")

        def _normalize_for_compare(qid: str, value: Any) -> Any:
            if value is None:
                return None
            if qid == "three-sum" and isinstance(value, list):
                try:
                    triplets = []
                    for t in value:
                        if isinstance(t, list):
                            triplets.append(sorted(t))
                        else:
                            triplets.append(t)
                    return sorted(triplets, key=lambda x: "|".join(map(str, x)) if isinstance(x, list) else str(x))
                except Exception:
                    return value
            if qid == "top-k-frequent" and isinstance(value, list):
                try:
                    return sorted(value)
                except Exception:
                    return value
            if qid == "group-anagrams" and isinstance(value, list):
                normalized_groups = []
                for g in value:
                    if isinstance(g, list):
                        try:
                            normalized_groups.append(sorted(g))
                        except Exception:
                            normalized_groups.append(g)
                    else:
                        normalized_groups.append(g)
                try:
                    return sorted(
                        normalized_groups,
                        key=lambda grp: "|".join(map(str, grp)) if isinstance(grp, list) else str(grp),
                    )
                except Exception:
                    return normalized_groups
            return value

        for idx, test_case in enumerate(test_cases):
            test_input = test_case["input"]
            expected_output = test_case["expectedOutput"]
            
            # Execute code based on language
            if request.language == "python":
                actual_output, error = execute_python_code(request.code, test_input, function_name)
            elif request.language == "javascript":
                actual_output, error = execute_javascript_code(request.code, test_input, function_name)
            else:
                actual_output, error = None, "Unsupported language"
            
            # Compare results
            passed = False
            if error:
                passed = False
                actual_output = None
            else:
                # Deep comparison of results
                qid = question["id"]
                passed = compare_outputs(
                    _normalize_for_compare(qid, actual_output),
                    _normalize_for_compare(qid, expected_output),
                )

            print(f"Test {idx + 1}: Expected={expected_output}, Actual={actual_output}, Passed={passed}, Error={error}")

            test_results.append({
                "test_case": idx + 1,
                "input": test_input,
                "expected_output": expected_output,
                "actual_output": actual_output,
                "passed": passed,
                "error": error
            })

            if passed:
                passed_count += 1

        # Calculate base score from test cases
        score = (passed_count / total_tests) * 100 if total_tests > 0 else 0
        all_passed = passed_count == total_tests

        # Analyze time complexity if submitted using AI
        efficiency_analysis = None
        is_efficient = True
        if request.run_mode == "submit" and all_passed:
            # Use AI to analyze time complexity
            efficiency_analysis = await analyze_time_complexity_with_ai(
                request.code,
                question.get("title", ""),
                question.get("description", ""),
                request.language
            )
            is_efficient = efficiency_analysis.get("is_optimal", True)

        print(f"Final results: {passed_count}/{total_tests} passed, score={score}%, is_efficient={is_efficient}")
        print(f"Test results array length: {len(test_results)}")
        if efficiency_analysis:
            print(f"Efficiency analysis: {efficiency_analysis}")

        return JSONResponse(content={
            "passed": all_passed,
            "score": round(score, 1),
            "passed_tests": passed_count,
            "total_tests": total_tests,
            "test_results": test_results,
            "is_efficient": is_efficient,
            "efficiency_analysis": efficiency_analysis
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


def compare_outputs(actual: Any, expected: Any) -> bool:
    """Compare actual and expected outputs, handling nested JSON-ish structures."""
    # Handle None cases
    if actual is None and expected is None:
        return True
    if actual is None or expected is None:
        return False

    # Dicts
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            return False
        for k in actual.keys():
            if not compare_outputs(actual.get(k), expected.get(k)):
                return False
        return True

    # Lists / tuples
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        if len(actual) != len(expected):
            return False
        return all(compare_outputs(a, b) for a, b in zip(actual, expected))

    # Primitive / fallback
    try:
        return actual == expected
    except Exception:
        return str(actual) == str(expected)


@app.post("/api/start-voice-interview")
async def start_voice_interview(request: VoiceInterviewRequest):
    """Start a voice interview session."""
    try:
        import uuid
        session_id = str(uuid.uuid4())
        
        # Initialize session
        interview_sessions[session_id] = {
            "questions_asked": 0,  # Will be set to 1 after first question is generated
            "max_questions": 3,
            "current_question": None,
            "conversation_history": [],
            "scores": []
        }
        
        # Generate first question using Gemini
        prompt = f"""You are an interviewer at {request.company} conducting a behavioral interview for a {request.role} position.
        Generate the first behavioral interview question. Make it relevant to the role and company culture.
        Keep it concise and professional (1-2 sentences). Just return the question, nothing else."""
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = await call_gemini_with_retry_async(
            client=client,
            model="gemini-2.5-flash",
            contents=prompt,
            max_retries=3,
            initial_delay=2
        )

        first_question = response.text.strip()
        interview_sessions[session_id]["current_question"] = first_question
        interview_sessions[session_id]["questions_asked"] = 1  # Track actual count of questions asked
        interview_sessions[session_id]["company"] = request.company
        interview_sessions[session_id]["role"] = request.role
        interview_sessions[session_id]["conversation_history"].append({
            "role": "interviewer",
            "content": first_question
        })
        
        print(f"[DEBUG] Started interview for {request.role} at {request.company}")
        print(f"[DEBUG] Session {session_id}: questions_asked = 1, max_questions = 3")

        print(f"[DEBUG] Start interview response: question_number=1")
        return JSONResponse(content={
            "session_id": session_id,
            "first_question": first_question,
            "question_number": 1,
            "total_questions": 3
        })
    except Exception as e:
        print(f"Error starting interview: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


@app.post("/api/voice-response")
async def handle_voice_response(
    audio: UploadFile = File(...),
    session_id: str = Form(...)
):
    """Process voice response with real transcription and interactive conversation."""
    try:
        if session_id not in interview_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = interview_sessions[session_id]
        
        # Transcribe audio using Google Gemini
        audio_content = await audio.read()
        
        transcript = ""
        
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # Prepare audio for Gemini (base64 encode)
            audio_b64 = base64.b64encode(audio_content).decode('utf-8')
            
            # Use Gemini to transcribe the audio
            prompt_parts = [
                {
                    "text": "Please transcribe the following audio recording. Provide ONLY the transcription, without any additional commentary or formatting. If the audio is unclear or silent, respond with '[inaudible]'."
                },
                {
                    "inline_data": {
                        "mime_type": "audio/wav",
                        "data": audio_b64
                    }
                }
            ]
            
            response = await call_gemini_with_retry_async(
                client=client,
                model="gemini-2.5-flash",  # Supports audio input
                contents=prompt_parts,
                max_retries=2,
                initial_delay=1
            )

            transcript = response.text.strip()
            print(f"[Gemini] Transcribed: {transcript[:100]}...")
            
        except Exception as e:
            print(f"[ERROR] Gemini transcription failed: {str(e)}")
            transcript = "[Audio transcription unavailable]"
        
        # Add user response to conversation history
        session["conversation_history"].append({
            "role": "candidate",
            "content": transcript
        })
        
        # Evaluate response quality based on scoring criteria
        evaluation_prompt = f"""You are an expert behavioral interview evaluator. Rate this response from the candidate on a scale of 0-100 based on these criteria:

SCORING CRITERIA:
1. Communication & Clarity (0-25): How clearly did they articulate their thoughts? Did they structure their answer well?
2. Relevance & Specificity (0-25): Did they provide specific examples? Is their answer relevant to the question?
3. Problem-Solving Approach (0-25): For conflict/challenge questions, did they show a constructive approach? Did they learn from the experience?
4. Professionalism & Cultural Fit (0-25): Does their response align with professional standards? Would they fit well in a team environment?

Candidate's Response: "{transcript}"

Respond with ONLY a number from 0-100 based on how well the response meets these criteria."""
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        eval_response = await call_gemini_with_retry_async(
            client=client,
            model="gemini-2.5-flash",
            contents=evaluation_prompt,
            max_retries=3,
            initial_delay=2
        )

        try:
            response_score = float(eval_response.text.strip())
            response_score = max(0, min(100, response_score))  # Clamp 0-100
        except:
            response_score = 50.0
        
        session["scores"].append(response_score)
        
        # Check how many responses we've received
        num_responses_received = len(session["scores"])
        
        print(f"[DEBUG] Received response #{num_responses_received}. Current scores: {session['scores']}")
        
        # If we've received 3 responses, interview is complete
        if num_responses_received >= session["max_questions"]:
            # Calculate final score
            final_score = sum(session["scores"]) / len(session["scores"]) if session["scores"] else 0
            
            # Round to nearest integer
            final_score = round(final_score)
            
            return JSONResponse(content={
                "next_question": None,
                "score": final_score,
                "completed": True,
                "individual_scores": session["scores"],
                "average_score": final_score
            })
        
        # Increment questions_asked to track the next question number
        print(f"[DEBUG] Session before increment - questions_asked: {session.get('questions_asked', 'NOT SET')}, session keys: {session.keys()}")

        # Ensure questions_asked is initialized
        if "questions_asked" not in session:
            session["questions_asked"] = 1

        session["questions_asked"] += 1
        next_question_number = session["questions_asked"]
        print(f"[DEBUG] After incrementing: questions_asked = {next_question_number}")
        
        # Generate next question
        prompt = f"""You are a professional interviewer at {session.get('company', 'a company')} conducting a behavioral interview for a {session.get('role', 'role')} position.

Current conversation:
{chr(10).join([f"{msg['role'].title()}: {msg['content']}" for msg in session["conversation_history"]])}

You have asked {next_question_number - 1} questions so far and are now asking question {next_question_number} of {session["max_questions"]}.

Generate question #{next_question_number}. Make it:
- Different from the previous question(s)
- Relevant to the role and company
- A behavioral question (past experience, how would you handle, tell me about a time, etc.)
- Concise and professional (1-2 sentences)

Return ONLY the question, nothing else."""
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = await call_gemini_with_retry_async(
            client=client,
            model="gemini-2.5-flash",
            contents=prompt,
            max_retries=3,
            initial_delay=2
        )

        next_response = response.text.strip()

        print(f"[DEBUG] Returning question #{next_question_number} after receiving {num_responses_received} responses")
        print(f"[DEBUG] Question text: {next_response[:100]}...")
        
        # Store new question in session
        session["current_question"] = next_response
        session["conversation_history"].append({
            "role": "interviewer",
            "content": next_response
        })

        print(f"[DEBUG] Returning question_number: {next_question_number}, completed: False")

        return JSONResponse(content={
            "next_question": next_response,
            "question_number": next_question_number,
            "total_questions": session["max_questions"],
            "completed": False
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing response: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


async def evaluate_interview_performance(interview_state: dict, client: genai.Client) -> dict:
    """
    Evaluate the candidate's performance based on the conversation history.
    Returns a dict with score and metadata.
    """
    try:
        scoring_version = "star_v3_guardrails_2026-01-13"

        # Extract conversation for evaluation
        conversation = interview_state.get("conversation_history", [])

        if not conversation:
            print("[Evaluation] No conversation history found, returning default score")
            return {"score": 50, "disqualified": False, "flags": {}, "scoring_version": scoring_version}

        # Build conversation text
        conversation_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in conversation
        ])

        # Deterministic disqualifying-content guardrail.
        # If the transcript contains threats/violence/illegal intent/unethical intent, hard-cap the score.
        try:
            def _norm_text(s: str) -> str:
                return re.sub(r"\s+", " ", (s or "").strip())

            def _extract_candidate_answers(conv: list[dict], max_answers: int) -> list[str]:
                # Conversation history can contain incremental transcripts; de-dupe to get
                # one best-effort string per answer.
                answers: list[str] = []
                for msg in conv:
                    if not isinstance(msg, dict) or msg.get("role") != "candidate":
                        continue
                    t = _norm_text(str(msg.get("content", "")))
                    if not t:
                        continue
                    if not answers:
                        answers.append(t)
                        continue
                    prev = answers[-1]
                    # Replace if it's an updated/longer version of the same transcript.
                    if t in prev:
                        continue
                    if prev in t:
                        answers[-1] = t
                        continue
                    answers.append(t)
                if max_answers > 0 and len(answers) > max_answers:
                    answers = answers[-max_answers:]
                return answers

            def _is_nonsense_answer(text: str) -> bool:
                t = _norm_text(text)
                if not t:
                    return True
                lower = t.casefold()

                # Common non-answers / filler.
                if re.search(r"\b(pass|skip|n/?a|no\s+comment|prefer\s+not\s+to\s+say)\b", lower):
                    return True
                if re.search(r"\b(idk|i\s+don'?t\s+know|no\s+idea|whatever)\b", lower) and len(lower) < 120:
                    return True
                if re.search(r"\b(asdf|qwer|lorem|ipsum|blah)\b", lower):
                    return True

                words = re.findall(r"[a-zA-Z']+", lower)
                wc = len(words)
                if wc < 6:
                    return True
                uniq = len(set(words))
                uniq_ratio = uniq / max(1, wc)
                # Repeating the same word over and over.
                from collections import Counter
                top = Counter(words).most_common(1)[0][1] if words else 0
                if wc >= 10 and (top / wc) >= 0.45:
                    return True
                # Mostly non-alphabetic characters.
                alpha = len(re.findall(r"[A-Za-z]", t))
                non_ws = len(re.findall(r"\S", t))
                if non_ws > 0 and (alpha / non_ws) < 0.35:
                    return True
                # Extremely low lexical diversity in a longer answer.
                if wc >= 25 and uniq_ratio < 0.25:
                    return True

                return False

            max_answers = int(interview_state.get("max_questions", 3) or 3)
            candidate_answers = _extract_candidate_answers(conversation, max_answers=max_answers)
            candidate_text = "\n".join(candidate_answers).strip()
            ct = candidate_text.casefold()

            # Deterministic disqualification for clearly unacceptable workplace behavior admissions.
            # (Even if the model evaluator misses it.)
            if re.search(r"\b(i\s*(always|usually|often)\s*)?(yell|scream|shout)\b", ct) and re.search(r"\b(coworker|co-worker|colleague|manager|team|people)\b", ct):
                print("[Evaluation] Disqualifying content detected: admits yelling at coworkers")
                return {
                    "score": 5,
                    "disqualified": True,
                    "flags": {"unprofessional": True, "harassment_hate": False, "sexual": False, "violence_threat": False},
                    "scoring_version": scoring_version,
                }

            # Deterministic disqualification for admissions of intentional non-performance/abandonment.
            # Examples: "I did no work", "I took zero action", "I left my team", "I never came back".
            no_work = re.search(
                r"\b(i\s*(did|do)\s*(no|zero)\s*(work|action)|i\s*(did|do)\s*nothing|"
                r"didn'?t\s*really\s*do\s*any\s*work|took\s*(no|zero)\s*action|"
                r"i\s*(never|didn'?t)\s*(help|contribute)|i\s*(didn'?t)\s*(contribute|participate))\b",
                ct,
            )
            abandonment = re.search(
                r"\b(left\s+(my\s+)?team\s+(to\s+)?(handle|do)\s+(it\s+)?(by\s+)?themselves|"
                r"i\s*(went|left)\s+.*\s+and\s+never\s+came\s+back|ghosted|abandoned|"
                r"i\s*(just\s*)?stopped\s*(working|showing\s+up)|no\s*show)\b",
                ct,
            )
            if no_work or abandonment:
                print("[Evaluation] Disqualifying content detected: admits no work / abandonment")
                return {
                    "score": 10,
                    "disqualified": True,
                    "flags": {"unprofessional": True, "harassment_hate": False, "sexual": False, "violence_threat": False},
                    "scoring_version": scoring_version,
                }

            # Vague but clearly disqualifying intent.
            vague_threat = re.search(r"\b(i\s*(would|'d)\s*do|i\s*will\s*do)\b[\s\S]{0,40}\b(bad\s+things|something\s+bad)\b", ct)

            # Explicit violence/threat language.
            violence = re.search(r"\b(kill|murder|shoot|stab|bomb|rape|assault|attack|hurt|harm)\b", ct)

            # Illegal/unethical intent.
            unethical = re.search(r"\b(steal|fraud|scam|embezzle|sabotage|blackmail|extort|leak\s+secrets|dox|hack)\b", ct)

            # Conditional intent tied to hiring/employment context.
            employment_context = re.search(r"\b(if\s+i\s*(get|got)\s+hired|if\s+you\s+hire\s+me|once\s+i\'?m\s+hired)\b", ct)

            if candidate_text:
                if violence:
                    print("[Evaluation] Disqualifying content detected: violence/threat")
                    return {
                        "score": 5,
                        "disqualified": True,
                        "flags": {"unprofessional": True, "harassment_hate": False, "sexual": False, "violence_threat": True},
                        "scoring_version": scoring_version,
                    }
                if unethical:
                    print("[Evaluation] Disqualifying content detected: illegal/unethical intent")
                    return {
                        "score": 10,
                        "disqualified": True,
                        "flags": {"unprofessional": True, "harassment_hate": False, "sexual": False, "violence_threat": False},
                        "scoring_version": scoring_version,
                    }
                if vague_threat and employment_context:
                    print("[Evaluation] Disqualifying content detected: vague threat in hiring context")
                    return {
                        "score": 10,
                        "disqualified": True,
                        "flags": {"unprofessional": True, "harassment_hate": False, "sexual": False, "violence_threat": False},
                        "scoring_version": scoring_version,
                    }

                # Deterministic nonsense/non-answer caps.
                if candidate_answers:
                    nonsense_flags = [
                        _is_nonsense_answer(a)
                        for a in candidate_answers
                    ]
                    nonsense_count = sum(1 for x in nonsense_flags if x)
                    if nonsense_count == len(candidate_answers):
                        print("[Evaluation] All candidate answers appear to be nonsense/non-answers")
                        return {"score": 0, "disqualified": True, "flags": {"unprofessional": True}, "scoring_version": scoring_version}
                    if nonsense_count >= 2:
                        print(f"[Evaluation] Majority nonsense/non-answers ({nonsense_count}/{len(candidate_answers)})")
                        return {"score": 5, "disqualified": True, "flags": {"unprofessional": True}, "scoring_version": scoring_version}
                    if nonsense_count == 1:
                        # One non-answer should heavily penalize overall score.
                        print("[Evaluation] At least one answer appears to be nonsense/non-answer")
                        # Don't return immediately; allow model scoring but cap later.
        except Exception:
            # Never fail evaluation due to guardrail checks.
            pass

        # STAR-based evaluation prompt (JSON) with explicit penalties.
        evaluation_prompt = f"""You are an expert behavioral interview evaluator.

You must score the CANDIDATE using the STAR method per answer:
- Situation (S): context and constraints
- Task (T): responsibility/goal
- Action (A): specific actions they personally took
- Result (R): outcome and impact (metrics preferred)

INTERVIEW DETAILS:
Company: {interview_state.get('company', 'Unknown')}
Role: {interview_state.get('role', 'Unknown')}

CONVERSATION TRANSCRIPT:
{conversation_text}

SCORING RULES:
1) Score each candidate answer on:
    - STAR completeness: S/T/A/R each 0-5
    - Communication (0-5): clear, structured, concise
    - Relevance (0-5): answers the question, specific example
    - Professionalism (0-5): respectful, workplace-appropriate
2) Compute an overall_score (0-100) that primarily reflects the average quality across answers.
3) STRICT PENALTIES:
    - If the candidate uses hateful/harassing language, threats, sexual content, violence, or expresses intent to do harmful/illegal/unethical actions (even vaguely), the overall_score must be severely reduced.
    - If content would disqualify a candidate in a real interview, overall_score should be 0-20.

OUTPUT FORMAT:
Return STRICT JSON only (no markdown, no commentary), with exactly these keys:
{{
  "overall_score": <integer 0-100>,
  "flags": {{
     "unprofessional": <true|false>,
     "harassment_hate": <true|false>,
     "sexual": <true|false>,
     "violence_threat": <true|false>
  }},
  "per_answer": [
     {{
        "answer_index": <1-based integer>,
        "star": {{"s": <0-5>, "t": <0-5>, "a": <0-5>, "r": <0-5>}},
        "communication": <0-5>,
        "relevance": <0-5>,
        "professionalism": <0-5>,
        "score_0_100": <integer 0-100>
     }}
  ]
}}
"""

        # Call Gemini for evaluation
        response = await asyncio.to_thread(
            call_gemini_with_retry,
            client=client,
            model="gemini-2.5-flash",
            contents=evaluation_prompt,
            max_retries=3,
            initial_delay=2
        )

        raw = (response.text or "").strip()
        parsed = None
        try:
            parsed = json.loads(raw)
        except Exception:
            # Try to salvage a JSON object embedded in text.
            import re
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except Exception:
                    parsed = None

        if isinstance(parsed, dict) and "overall_score" in parsed:
            score = int(parsed.get("overall_score", 0))
            score = max(0, min(100, score))

            flags = parsed.get("flags") if isinstance(parsed.get("flags"), dict) else {}
            harassment_hate = bool(flags.get("harassment_hate"))
            sexual = bool(flags.get("sexual"))
            violence_threat = bool(flags.get("violence_threat"))
            unprofessional = bool(flags.get("unprofessional"))

            disqualified = False

            # Hard caps for disqualifying content.
            if harassment_hate or sexual or violence_threat:
                score = min(score, 15)
                disqualified = True
            if unprofessional:
                score = min(score, 35)

            # Additional cap if any per-answer professionalism is extremely low.
            per = parsed.get("per_answer") if isinstance(parsed.get("per_answer"), list) else []
            try:
                min_prof = min(int(a.get("professionalism", 5)) for a in per if isinstance(a, dict)) if per else 5
                if min_prof <= 1:
                    score = min(score, 20)
                    disqualified = True
            except Exception:
                pass

            # If any answer is clearly a non-answer/nonsense, cap the overall score.
            try:
                max_answers = int(interview_state.get("max_questions", 3) or 3)
                candidate_answers = []
                for msg in conversation:
                    if not isinstance(msg, dict) or msg.get("role") != "candidate":
                        continue
                    t = re.sub(r"\s+", " ", str(msg.get("content", "")).strip())
                    if not t:
                        continue
                    if not candidate_answers:
                        candidate_answers.append(t)
                        continue
                    prev = candidate_answers[-1]
                    if t in prev:
                        continue
                    if prev in t:
                        candidate_answers[-1] = t
                        continue
                    candidate_answers.append(t)
                if max_answers > 0 and len(candidate_answers) > max_answers:
                    candidate_answers = candidate_answers[-max_answers:]

                def _is_nonsense_quick(text: str) -> bool:
                    lower = re.sub(r"\s+", " ", (text or "").strip()).casefold()
                    if not lower:
                        return True
                    if re.search(r"\b(pass|skip|n/?a|no\s+comment)\b", lower):
                        return True
                    words = re.findall(r"[a-zA-Z']+", lower)
                    if len(words) < 6:
                        return True
                    return False

                nonsense_count = sum(1 for a in candidate_answers if _is_nonsense_quick(a))
                if candidate_answers and nonsense_count == len(candidate_answers):
                    score = min(score, 0)
                    disqualified = True
                elif nonsense_count >= 2:
                    score = min(score, 5)
                    disqualified = True
                elif nonsense_count == 1:
                    score = min(score, 20)
            except Exception:
                pass

            print(f"[Evaluation] STAR score: {score} (flags={flags}, disqualified={disqualified})")
            return {"score": score, "disqualified": disqualified, "flags": flags, "scoring_version": scoring_version}

        # If parsing fails, fall back conservatively (do not return a generous score).
        print(f"[Evaluation] Could not parse STAR JSON from: {raw[:200]}...")
        return {"score": 40, "disqualified": False, "flags": {}, "scoring_version": scoring_version}

    except Exception as e:
        print(f"[Evaluation] Error evaluating performance: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"score": 40, "disqualified": False, "flags": {}, "scoring_version": "star_v3_guardrails_2026-01-13"}


@app.websocket("/ws/behavioral-interview")
async def behavioral_interview_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time behavioral interview using Gemini Live API."""
    print(f"[WebSocket] New connection attempt...")
    try:
        # Accept WebSocket connection
        await websocket.accept()
        print(f"[WebSocket] Connection accepted from client")
    except Exception as e:
        print(f"[WebSocket] Failed to accept connection: {str(e)}")
        import traceback
        traceback.print_exc()
        return

    try:
        # Receive initial connection data (company, role, resume)
        init_data = await websocket.receive_json()
        company = init_data.get("company", "a company")
        role = init_data.get("role", "a role")
        resume_text = init_data.get("resume_text", "")

        import uuid
        session_id = str(uuid.uuid4())

        print(f"[WebSocket] Starting behavioral interview for {role} at {company}")
        print(f"[WebSocket] Session ID: {session_id}")
        print(f"[WebSocket] Resume text received: {len(resume_text)} chars" if resume_text else "[WebSocket] No resume text received")

        # Initialize interview session state
        interview_state = {
            "questions_asked": 0,
            "answers_completed": 0,
            "max_questions": 3,
            "questions": [],
            "scores": [],
            "conversation_history": [],
            "candidate_answers": {},
            "server_transcripts": {},
            "answers_recorded": set(),
            "company": company,
            "role": role
        }

        # Configure Gemini Live API
        client = genai.Client(api_key=GEMINI_API_KEY)
        MODEL = "gemini-2.0-flash-exp"

        # Pre-generate canonical questions (clean UI text) using a non-Live model.
        # This avoids relying on output_audio_transcription, which can be garbled.
        async def generate_questions_with_prompt(prompt: str) -> list:
            """Helper to generate questions from a prompt and parse the JSON response."""
            q_resp = await asyncio.to_thread(
                call_gemini_with_retry,
                client,
                "gemini-2.5-flash",
                prompt,
                3,
                2,
            )

            # Get response text, handling different response structures
            resp_text = ""
            if hasattr(q_resp, 'text') and q_resp.text:
                resp_text = q_resp.text.strip()
            elif hasattr(q_resp, 'candidates') and q_resp.candidates:
                for candidate in q_resp.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    resp_text = part.text.strip()
                                    break
                    if resp_text:
                        break

            if not resp_text:
                if hasattr(q_resp, 'prompt_feedback'):
                    print(f"[WebSocket] Prompt feedback: {q_resp.prompt_feedback}")
                raise ValueError("Empty response from Gemini")

            # Extract JSON from response (handle markdown code blocks)
            json_text = resp_text
            if "```json" in resp_text:
                json_text = resp_text.split("```json")[1].split("```")[0].strip()
            elif "```" in resp_text:
                json_text = resp_text.split("```")[1].split("```")[0].strip()

            parsed = json.loads(json_text)
            questions = parsed.get("questions") if isinstance(parsed, dict) else None
            if not isinstance(questions, list) or len(questions) != 3:
                raise ValueError(f"Invalid questions format: {json_text[:200]}")
            return [str(q).strip() for q in questions if str(q).strip()]

        try:
            # Strategy 1: Try personalized questions if resume is available
            if resume_text and resume_text.strip():
                try:
                    print(f"[WebSocket] Attempting personalized question generation...")
                    personalized_prompt = (
                        f"Generate exactly 3 behavioral interview questions for a {role} role at {company}.\n\n"
                        f"The candidate's resume:\n{resume_text[:2000]}\n\n"  # Limit resume length
                        "IMPORTANT: Generate questions in this mix:\n"
                        "- Question 1: A general behavioral question (teamwork, conflict resolution, or communication)\n"
                        "- Question 2: A general behavioral question about problem-solving or taking initiative\n"
                        "- Question 3: A PERSONALIZED question based on a specific experience, project, or skill from their resume. "
                        "Reference something concrete from their background.\n\n"
                        "Each question must be 1-2 concise sentences, professional, and relevant to the role.\n"
                        "Return STRICT JSON only: {\"questions\": [\"...\", \"...\", \"...\"]}"
                    )
                    questions = await generate_questions_with_prompt(personalized_prompt)
                    interview_state["questions"] = questions
                    print(f"[WebSocket] Generated personalized questions: {questions}")
                except Exception as personalized_err:
                    print(f"[WebSocket] Personalized generation failed: {personalized_err}")
                    # Fall through to generic generation
                    raise personalized_err
            else:
                # Strategy 2: Generic questions (no resume)
                generic_prompt = (
                    f"Generate exactly 3 distinct behavioral interview questions for a {role} role at {company}.\n"
                    "Each question must be 1-2 concise sentences, professional, and relevant to the role.\n"
                    "Return STRICT JSON only: {\"questions\": [\"...\", \"...\", \"...\"]}"
                )
                questions = await generate_questions_with_prompt(generic_prompt)
                interview_state["questions"] = questions
                print(f"[WebSocket] Generated generic questions: {questions}")

        except Exception as e:
            # Strategy 3: Try generic questions as fallback if personalized failed
            if resume_text and resume_text.strip():
                try:
                    print(f"[WebSocket] Trying generic questions as fallback...")
                    generic_prompt = (
                        f"Generate exactly 3 distinct behavioral interview questions for a {role} role at {company}.\n"
                        "Each question must be 1-2 concise sentences, professional, and relevant to the role.\n"
                        "Return STRICT JSON only: {\"questions\": [\"...\", \"...\", \"...\"]}"
                    )
                    questions = await generate_questions_with_prompt(generic_prompt)
                    interview_state["questions"] = questions
                    print(f"[WebSocket] Generated generic fallback questions: {questions}")
                except Exception as generic_err:
                    print(f"[WebSocket] Generic generation also failed: {generic_err}, using hardcoded fallback")
                    interview_state["questions"] = [
                        "Tell me about a time you faced a challenging problem at work or school. What did you do and what was the outcome?",
                        "Describe a time you had to work with a difficult teammate or resolve a conflict. How did you handle it?",
                        "Tell me about a time you took initiative or led a project. What actions did you take and what did you learn?",
                    ]
            else:
                print(f"[WebSocket] Failed to pre-generate questions, using hardcoded fallback: {e}")
                interview_state["questions"] = [
                    "Tell me about a time you faced a challenging problem at work or school. What did you do and what was the outcome?",
                    "Describe a time you had to work with a difficult teammate or resolve a conflict. How did you handle it?",
                    "Tell me about a time you took initiative or led a project. What actions did you take and what did you learn?",
                ]

        # System instruction for the interview
        system_instruction = f"""You are a professional behavioral interviewer at {company} conducting an interview for a {role} position.

CRITICAL INSTRUCTIONS:
1. When you receive a message, it will contain ONLY the interview question you should ask.
2. Speak the question naturally and clearly, exactly as provided - do not add any preamble or extra words.
3. Do NOT read out any meta-instructions or acknowledge them verbally - just ask the question provided.
4. Do NOT interrupt the candidate while they are speaking. Wait for long pauses (3+ seconds).
5. Do NOT use filler words like "okay", "mm-hmm", or "I see" during the candidate's response.
6. After the candidate finishes their answer, remain completely silent unless you receive another message.
7. Never ask follow-up questions unless explicitly instructed.

Remember: You only speak when given a new message. Each message contains exactly what you should say."""

        config = {
            # Note: Live API expects a single output modality. Requesting both
            # AUDIO and TEXT can cause a 1007 "invalid argument" during connect.
            "response_modalities": ["AUDIO"],
            # Ask Gemini to include transcripts alongside audio.
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "system_instruction": {
                "role": "system",
                "parts": [{"text": system_instruction}]
            },
            # Configure voice and turn detection
            "generation_config": {
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": "Puck"
                        }
                    }
                }
            }
        }

        print(f"[WebSocket] Connecting to Gemini Live API...")

        try:
            # Connect to Gemini Live API
            async with client.aio.live.connect(model=MODEL, config=config) as session:
                print(f"[WebSocket] Connected to Gemini Live API")

                import time

                def _merge_transcript(prev: str, chunk: str) -> str:
                    """Merge incremental transcript chunks without flicker/duplication."""
                    if not chunk:
                        return prev
                    if not prev:
                        return chunk
                    if chunk in prev:
                        return prev
                    # If chunk looks like a full replacement (much longer), prefer it.
                    if len(chunk) > len(prev) and prev in chunk:
                        return chunk
                    # If chunk already starts with prev, treat as a replacement update.
                    if chunk.startswith(prev):
                        return chunk
                    # Overlap merge: find max suffix of prev that's a prefix of chunk.
                    max_overlap = min(80, len(prev), len(chunk))
                    for k in range(max_overlap, 0, -1):
                        if prev[-k:] == chunk[:k]:
                            return prev + chunk[k:]
                    # Fallback: concatenate without injecting spaces.
                    # (The transcription stream may be character-level; adding spaces makes it unreadable.)
                    return prev + chunk

                def _normalize_transcript(text: str) -> str:
                    return re.sub(r"\s+", " ", (text or "").strip())

                def _store_candidate_transcript(question_number: int, text: str) -> None:
                    if not isinstance(question_number, int) or question_number <= 0:
                        return
                    normalized = _normalize_transcript(text)
                    if not normalized:
                        return
                    interview_state.setdefault("candidate_answers", {})[question_number] = normalized

                def _record_candidate_answer(question_number: int) -> None:
                    if not isinstance(question_number, int) or question_number <= 0:
                        return
                    recorded = interview_state.setdefault("answers_recorded", set())
                    if question_number in recorded:
                        return

                    answers = interview_state.get("candidate_answers", {}) or {}
                    text = answers.get(question_number, "")
                    if not text:
                        text = (interview_state.get("server_transcripts", {}) or {}).get(question_number, "")
                    text = _normalize_transcript(text)
                    if not text:
                        text = "[inaudible]"

                    interview_state["conversation_history"].append({
                        "role": "candidate",
                        "content": text
                    })
                    recorded.add(question_number)

                # State for stable transcript streaming
                awaiting_question_turn_complete = True  # first model turn should be Q1
                awaiting_close_turn_complete = False
                last_out_sent = 0.0
                last_in_sent = 0.0
                received_audio_since_last_turn = False
                candidate_turn_active = False
                audio_bytes_since_last_turn = 0
                audio_chunks_since_last_turn = 0
                audio_first_ts = None
                audio_last_ts = None
                current_question_in_flight = 0

                async def _send_canonical_question(question_number: int, acknowledge_first: bool = False):
                    idx = question_number - 1
                    questions = interview_state.get("questions") or []
                    if idx < 0 or idx >= len(questions):
                        raise ValueError(f"Question index out of range: {question_number}")
                    q_text = questions[idx]

                    # Guardrail: never exceed max questions.
                    if question_number > interview_state["max_questions"]:
                        raise ValueError(f"Question number exceeds max_questions: {question_number}")

                    # Update UI with clean question text.
                    await websocket.send_json({
                        "type": "question",
                        "question_number": question_number,
                        "total_questions": interview_state["max_questions"],
                        "content": q_text,
                    })

                    # Store canonical interviewer question for evaluation.
                    interview_state["conversation_history"].append({
                        "role": "interviewer",
                        "content": q_text,
                    })

                    # Track question progression based on what we *send*, not model turn_complete.
                    nonlocal current_question_in_flight, awaiting_question_turn_complete
                    current_question_in_flight = question_number
                    awaiting_question_turn_complete = True
                    interview_state["questions_asked"] = max(interview_state["questions_asked"], question_number)
                    print(f"[WebSocket] Question {question_number} sent")

                    # Send ONLY the question text - no meta-instructions
                    # The system instruction already tells Gemini how to behave
                    if acknowledge_first:
                        instruction = f"Thank you. {q_text}"
                    else:
                        instruction = q_text

                    await session.send_realtime_input(text=instruction)

                # Kick off with Q1 (canonical text + spoken verbatim).
                await _send_canonical_question(1, acknowledge_first=False)

                # Create tasks for bidirectional communication
                async def receive_from_gemini():
                    """Receive responses from Gemini and forward to frontend"""
                    try:
                        nonlocal last_out_sent, last_in_sent, received_audio_since_last_turn
                        nonlocal awaiting_question_turn_complete, awaiting_close_turn_complete
                        nonlocal candidate_turn_active, current_question_in_flight
                        done = False
                        while not done:
                            # Reset per-model-turn transcript buffers.
                            out_transcript_local = ""
                            in_transcript_local = ""

                            # Note: google-genai's session.receive() yields messages for a single
                            # model turn and then stops when turn_complete is seen.
                            async for response in session.receive():
                                # Handle user transcript (candidate's speech recognized by Gemini)
                                if hasattr(response, 'user_turn') and response.user_turn:
                                    user_turn = response.user_turn
                                    if hasattr(user_turn, 'parts') and user_turn.parts:
                                        for part in user_turn.parts:
                                            if hasattr(part, 'text') and part.text:
                                                user_text = part.text
                                                print(f"[User] Response (server transcript): {user_text[:100]}...")

                                # Handle server content (audio from Gemini)
                                if response.server_content:
                                    # Forward server-side transcriptions (works in AUDIO mode)
                                    if response.server_content.input_transcription and getattr(response.server_content.input_transcription, 'text', None):
                                        nonlocal_in = response.server_content.input_transcription.text
                                        in_transcript_local = _merge_transcript(in_transcript_local, nonlocal_in)
                                        now = time.monotonic()
                                        if now - last_in_sent >= 0.12 or getattr(response.server_content.input_transcription, 'finished', False):
                                            last_in_sent = now
                                            try:
                                                await websocket.send_json({
                                                    "type": "text",
                                                    "content": in_transcript_local,
                                                    "speaker": "candidate"
                                                })
                                            except Exception:
                                                pass
                                        if getattr(response.server_content.input_transcription, 'finished', False):
                                            interview_state.setdefault("server_transcripts", {})[current_question_in_flight] = in_transcript_local

                                    if response.server_content.output_transcription and getattr(response.server_content.output_transcription, 'text', None):
                                        # Intentionally ignored: output transcription is often garbled.
                                        # UI uses canonical questions instead.
                                        pass

                                    model_turn = response.server_content.model_turn
                                    if model_turn and model_turn.parts:
                                        # Only forward interviewer audio while the interviewer is speaking
                                        # (i.e., during question delivery or closing). This prevents
                                        # any mid-answer interruptions or follow-ups from being heard.
                                        allow_audio = awaiting_question_turn_complete or awaiting_close_turn_complete
                                        for part in model_turn.parts:
                                            if hasattr(part, 'inline_data') and part.inline_data:
                                                if not allow_audio:
                                                    continue
                                                audio_data = part.inline_data.data
                                                mime_type = getattr(part.inline_data, 'mime_type', None)
                                                sample_rate = 24000
                                                if isinstance(mime_type, str):
                                                    import re
                                                    m = re.search(r'rate=(\d+)', mime_type)
                                                    if m:
                                                        try:
                                                            sample_rate = int(m.group(1))
                                                        except ValueError:
                                                            pass
                                                await websocket.send_json({
                                                    "type": "audio",
                                                    "format": "pcm_s16le",
                                                    "sample_rate": sample_rate,
                                                    "mime_type": mime_type,
                                                    "data": base64.b64encode(audio_data).decode('utf-8')
                                                })

                                            # Ignore any interviewer text to avoid follow-ups in UI/state
                                            if hasattr(part, 'text') and part.text:
                                                text_content = part.text
                                                print(f"[Gemini] (interviewer text ignored) {text_content[:100]}...")

                                    # Handle turn completion
                                    if response.server_content.turn_complete:
                                        if awaiting_question_turn_complete:
                                            # Mark end of interviewer speaking for the in-flight question.
                                            qn = current_question_in_flight
                                            print(f"[WebSocket] Interviewer finished Q{qn}")
                                            awaiting_question_turn_complete = False
                                            # Candidate may answer now.
                                            candidate_turn_active = True
                                            await websocket.send_json({
                                                "type": "turn_complete",
                                                "question_number": qn,
                                                "total_questions": interview_state["max_questions"],
                                            })
                                        elif awaiting_close_turn_complete:
                                            # Closing message finished; now evaluate.
                                            print(f"[WebSocket] Evaluating interview performance...")
                                            try:
                                                await websocket.send_json({
                                                    "type": "reviewing",
                                                    "message": "Your interview is being reviewed...",
                                                })
                                            except Exception:
                                                pass
                                            eval_result = await evaluate_interview_performance(interview_state, client)
                                            final_score = int(eval_result.get("score", 0))
                                            await websocket.send_json({
                                                "type": "interview_complete",
                                                "score": final_score,
                                                "disqualified": bool(eval_result.get("disqualified", False)),
                                                "flags": eval_result.get("flags", {}),
                                                "scoring_version": eval_result.get("scoring_version", "")
                                            })
                                            print(f"[WebSocket] Interview complete with score: {final_score}")
                                            done = True
                                            break

                            if done:
                                break

                    except Exception as e:
                        print(f"[WebSocket] Error receiving from Gemini: {str(e)}")
                        try:
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Error: {str(e)}"
                            })
                        except Exception:
                            pass

                async def send_to_gemini():
                    """Receive audio from frontend and send to Gemini"""
                    try:
                        nonlocal received_audio_since_last_turn
                        nonlocal awaiting_question_turn_complete, awaiting_close_turn_complete
                        nonlocal candidate_turn_active, current_question_in_flight
                        nonlocal audio_bytes_since_last_turn, audio_chunks_since_last_turn
                        nonlocal audio_first_ts, audio_last_ts

                        MIN_AUDIO_MS = 900
                        MIN_AUDIO_CHUNKS = 3
                        while True:
                            message = await websocket.receive_json()

                            if message.get("type") == "transcript_final":
                                qn = message.get("question_number")
                                text = message.get("text", "")
                                try:
                                    qn = int(qn)
                                except Exception:
                                    qn = current_question_in_flight
                                _store_candidate_transcript(qn, text)
                                continue

                            if message.get("type") == "audio":
                                # Ignore any stray audio while the interviewer is speaking.
                                if not candidate_turn_active:
                                    continue
                                received_audio_since_last_turn = True
                                # Decode base64 audio from frontend
                                audio_data = base64.b64decode(message.get("data", ""))

                                # Track how much candidate audio we actually received this turn.
                                now = time.monotonic()
                                if audio_first_ts is None:
                                    audio_first_ts = now
                                audio_last_ts = now
                                audio_bytes_since_last_turn += len(audio_data)
                                audio_chunks_since_last_turn += 1

                                # Send audio to Gemini using realtime input
                                from google.genai import types
                                await session.send_realtime_input(
                                    audio=types.Blob(data=audio_data, mime_type="audio/pcm;rate=16000")
                                )

                            elif message.get("type") == "end_of_turn":
                                # Ignore end_of_turn if we're not currently expecting an answer.
                                if not candidate_turn_active:
                                    continue

                                # If the client didn't detect real speech, don't advance the interview.
                                # This avoids moving on due to background noise / accidental triggers.
                                if message.get("had_speech") is False:
                                    print("[WebSocket] end_of_turn received with no speech; ignoring")
                                    received_audio_since_last_turn = False
                                    audio_bytes_since_last_turn = 0
                                    audio_chunks_since_last_turn = 0
                                    audio_first_ts = None
                                    audio_last_ts = None
                                    # Ask frontend to resume listening.
                                    try:
                                        await websocket.send_json({
                                            "type": "resume_listening",
                                            "reason": "no_speech"
                                        })
                                    except Exception:
                                        pass
                                    continue

                                # Minimum answer length guard (server-side): if we didn't receive enough
                                # audio, don't end the turn / advance to the next question.
                                # Assumes 16kHz mono PCM16.
                                audio_ms = int((audio_bytes_since_last_turn / (2 * 16000)) * 1000) if audio_bytes_since_last_turn else 0
                                if (audio_ms < MIN_AUDIO_MS) or (audio_chunks_since_last_turn < MIN_AUDIO_CHUNKS):
                                    print(f"[WebSocket] end_of_turn too short (audio_ms={audio_ms}, chunks={audio_chunks_since_last_turn}); requesting more")
                                    received_audio_since_last_turn = False
                                    audio_bytes_since_last_turn = 0
                                    audio_chunks_since_last_turn = 0
                                    audio_first_ts = None
                                    audio_last_ts = None
                                    try:
                                        await websocket.send_json({
                                            "type": "resume_listening",
                                            "reason": "too_short",
                                            "min_audio_ms": MIN_AUDIO_MS,
                                            "min_chunks": MIN_AUDIO_CHUNKS
                                        })
                                    except Exception:
                                        pass
                                    continue

                                # User finished speaking - signal end of turn
                                answered_q = current_question_in_flight
                                print(f"[WebSocket] User finished response for Q{answered_q}")
                                candidate_turn_active = False
                                _record_candidate_answer(answered_q)
                                # Explicitly signal end of audio stream; otherwise Gemini may wait.
                                await session.send_realtime_input(audio_stream_end=True)

                                # Give a short grace period so turn-taking feels natural.
                                # Prevents Gemini from speaking immediately when the user stops.
                                await asyncio.sleep(2.2)

                                # Only count an answer if we actually streamed some audio.
                                if received_audio_since_last_turn:
                                    received_audio_since_last_turn = False
                                    interview_state["answers_completed"] += 1

                                audio_bytes_since_last_turn = 0
                                audio_chunks_since_last_turn = 0
                                audio_first_ts = None
                                audio_last_ts = None

                                # Drive the conversation explicitly so we always advance.
                                if interview_state["answers_completed"] < interview_state["max_questions"]:
                                    next_q = interview_state["answers_completed"] + 1
                                    await _send_canonical_question(next_q, acknowledge_first=False)
                                elif interview_state["answers_completed"] >= interview_state["max_questions"]:
                                    # After the 3rd response, send a closing statement
                                    # Send ONLY what we want Gemini to say - no meta-instructions
                                    awaiting_close_turn_complete = True
                                    awaiting_question_turn_complete = False
                                    await session.send_realtime_input(
                                        text=f"Thank you for sharing your experiences with us today. We appreciate your time, and we'll be in touch soon regarding next steps."
                                    )

                    except WebSocketDisconnect:
                        print(f"[WebSocket] Client disconnected")
                    except Exception as e:
                        print(f"[WebSocket] Error sending to Gemini: {str(e)}")

                # Run both tasks concurrently (keep Gemini session open)
                await asyncio.gather(
                    receive_from_gemini(),
                    send_to_gemini()
                )

        except Exception as gemini_error:
            print(f"[WebSocket] Gemini Live API Error: {str(gemini_error)}")
            import traceback
            traceback.print_exc()
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Gemini connection failed: {str(gemini_error)}"
                })
            except:
                pass

    except WebSocketDisconnect:
        print(f"[WebSocket] Connection closed")
    except Exception as e:
        print(f"[WebSocket] General Error: {str(e)}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"An error occurred: {str(e)}"
            })
        except:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
