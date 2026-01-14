from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
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
from datetime import date
from google import genai
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

app = FastAPI(title="AI Resume Critique API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add WebSocket origins explicitly
ALLOWED_WS_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

# Session storage for behavioral interviews
interview_sessions = {}


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


def call_gemini_with_retry(client, model, contents, max_retries=3, initial_delay=1):
    """
    Call Gemini API with retry logic for 503 errors.
    
    Args:
        client: Gemini client instance
        model: Model name to use
        contents: Prompt/content to send
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
    
    Returns:
        Response from Gemini API
    
    Raises:
        Exception: If all retries fail or non-retryable error occurs
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents
            )
            return response
        except Exception as e:
            error_str = str(e)
            # Check if it's a 503 error (service unavailable/overloaded)
            # Handle various error formats from Gemini API
            is_503 = False
            
            # Check error string for 503 indicators
            if "503" in error_str or "UNAVAILABLE" in error_str.upper() or "overloaded" in error_str.lower():
                is_503 = True
            
            # Check if exception has error attribute with code 503
            if hasattr(e, 'error'):
                if isinstance(e.error, dict) and e.error.get('code') == 503:
                    is_503 = True
                elif isinstance(e.error, str) and ("503" in e.error or "UNAVAILABLE" in e.error.upper()):
                    is_503 = True
            
            # Check exception attributes directly
            if hasattr(e, 'status_code') and e.status_code == 503:
                is_503 = True
            if hasattr(e, 'code') and e.code == 503:
                is_503 = True
            
            if is_503 and attempt < max_retries:
                # Calculate exponential backoff delay
                delay = initial_delay * (2 ** attempt)
                time.sleep(delay)
                last_exception = e
                continue
            else:
                # Non-retryable error or max retries reached
                raise e
    
    # If we exhausted all retries, raise the last exception
    if last_exception:
        raise Exception(f"Service unavailable after {max_retries + 1} attempts. Please try again later. Original error: {str(last_exception)}")


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

        STARTUP LEVEL (Minimum acceptable - Score: 50-60):
        - First year university student at Waterloo
        - 1 current software development role (UW Orbital - Ground Station Developer with FastAPI/React)
        - 2-3 solid personal projects (hearth. real estate analyzer, housing price predictor, AI resume reviewer)
        - Some technical skills and certifications
        - Leadership/extracurriculars (case competitions)
        This candidate should score 50-60. Can pass startup level screening.

        INTERMEDIATE LEVEL (Minimum acceptable - Score: 70-80):
        - University student with good GPA If their GPA is low, require stronger projects/experience
        - 2+ years combined experience OR 2+ internships at known companies (not required, but preferred)
        - Example: Java Backend Engineer with 2 years at real companies, multiple projects
        - OR: Multiple solid projects + some work experience + strong academics
        - Production-level projects with real metrics
        - If they have less than 2 years of experience, require extremely high level projects, internships or experience
        This candidate should score 70-80. Can pass intermediate level screening.

        BIG TECH LEVEL (Minimum acceptable - Score: 80+):
        - MUST have: 2+ years of professional software development experience
        - Very relevant work + positions with large scale contributions in their role.
        - 2+ internships at different companies with quantified impact
        - OR: Multiple FAANG internships (Amazon SDE, Adobe Computer Scientist)
        - Clear evidence of working on large-scale systems (millions of users, significant cost savings)
        - Strong technical depth across multiple domains
        This candidate should score 80+. Ready for big tech.

        SCORING GUIDELINES:
        - 80+: Ready for Big Tech (FAANG level companies)
        - 60-79: Can pass intermediate/established company screening (max 80 if can pass intermediate)
        - 50-59: Can pass startup level screening (max 60 if can pass startup)
        - 40-49: Small shot at startup jobs, significant gaps
        - Under 40: Cannot pass any screening, major issues
        """

        prompt = f"""Today is {date.today()}.
        You are a hiring manager at a top company in the field of {job_role if job_role else "various industries"}.
        You have received a resume for review. Evaluate this resume against the reference examples provided.

        {reference_examples}

        RESUME TO REVIEW:
        {text_content}

        INSTRUCTIONS:
        1. Compare this resume to the REFERENCE resumes provided above
        2. Determine which level this resume can pass (startup, intermediate, or big tech)
        3. Assign a PRECISE score from 1-100 based on these STRICT SCORING GUIDELINES:
           - 0-30: Significantly below entry-level standards
           - 31-45: Below startup level, needs major improvements
           - 46-55: Startup level potential, needs improvements
           - 56-65: Solid startup level resume
           - 66-72: Low intermediate level (Canadian banks, mid-size companies)
           - 73-78: Strong intermediate level
           - 79-84: High intermediate level, approaching big tech
           - 85-91: Big tech ready with minor improvements
           - 92-96: Strong big tech resume
           - 97-100: Exceptional big tech resume
        4. Be STRICT and REALISTIC. Use the reference examples as your baseline.
        5. Provide a SPECIFIC numeric score (not rounded to 25, 50, 75, or 100).
        6. Provide structured feedback with specific recommendations.

        Respond in this EXACT format:
        SCORE: [number between 0-100]

        STRENGTHS:
        - [Bullet point 1]
        - [Bullet point 2]
        - [Bullet point 3]

        AREAS FOR IMPROVEMENT:
        - [Bullet point 1]
        - [Bullet point 2]
        - [Bullet point 3]

        RECOMMENDATIONS:
        - [Actionable recommendation 1]
        - [Actionable recommendation 2]
        - [Actionable recommendation 3]

        OVERALL ASSESSMENT:
        [2-3 sentences summarizing the resume's readiness level and main takeaways]

        Additional Notes: {additional_notes}
        Tailor your feedback for {job_role if job_role else "general applications"}
        """

        # Call Gemini API with retry logic
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = call_gemini_with_retry(
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
            score = int(score_match.group(1))
            # Clamp score to 0-100
            score = max(0, min(100, score))

        return JSONResponse(content={
            "success": True,
            "feedback": response_text,
            "score": score
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


@app.post("/api/screen-resume")
async def screen_resume(
    file: UploadFile = File(...),
    difficulty: str = Form(...),
    role: str = Form(...),
    level: str = Form(...)
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

        # Map difficulty to company tier and screening criteria
        difficulty_configs = {
            "easy": {
                "company_type": "an early-stage startup internship program",
                "strictness": """
                STARTUP INTERNSHIP HIRING MODE: Looking for promising candidates eager to learn and build.

                PASS if candidate has:
                - Currently enrolled in or recently completed university/bootcamp
                - 1+ relevant projects (personal, school, or previous internship)
                - Demonstrated passion for technology and learning
                - Basic competency in required tech stack
                - Previous internship experience is a plus

                REJECT if:
                - No programming experience whatsoever
                - Only theoretical knowledge without practical projects
                - Poor communication or lack of professional presence

                Target pass rate: ~50-60% of applicants
                """
            },
            "medium": {
                "company_type": "a mid-tier company internship program",
                "strictness": """
                MID-TIER COMPANY INTERNSHIP HIRING MODE: Looking for solid candidates with proven skills.

                PASS if candidate has:
                - Currently enrolled in or recently completed university
                - 2+ relevant projects demonstrating technical depth
                - Strong portfolio or GitHub presence
                - Relevant internship or professional experience preferred
                - Solid grasp of CS fundamentals
                - Clear communication and professional presence

                REJECT if:
                - Minimal programming experience or projects
                - No demonstrated technical growth
                - Weak academic standing in CS courses
                - Poor communication skills

                Target pass rate: ~30-40% of applicants
                """
            },
            "hard": {
                "company_type": "a Big Tech company internship program",
                "strictness": """
                BIG TECH INTERNSHIP HIRING MODE: Looking for top-tier candidates with exceptional skills.

                PASS if candidate has:
                - Strong academic background or completed bootcamp
                - 3+ meaningful projects with technical depth
                - Strong GitHub presence or competitive programming record
                - Previous internship at reputable company highly preferred
                - Excellent grasp of CS fundamentals and algorithms
                - Clear evidence of continuous learning and growth
                - Professional communication and leadership

                REJECT if:
                - Limited project portfolio
                - No evidence of competitive programming or algorithms knowledge
                - Weak academic standing
                - Generic or unprofessional presentation

                Target pass rate: ~15-25% of applicants
                """
            }
        }

        config = difficulty_configs.get(difficulty, difficulty_configs["easy"])
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
            REFERENCE: This is an acceptable resume for a mid-tier company internship:
            - University student with strong academics or bootcamp graduate
            - 2+ substantial projects demonstrating technical skills
            - Previous internship or freelance experience preferred
            - Clear evidence of CS fundamentals understanding

            This candidate should PASS a mid-tier internship screening. Use this as your baseline.
            """,
            "hard": """
            REFERENCE: This is an acceptable resume for a Big Tech internship:
            - Strong university background or rigorous bootcamp
            - 3+ significant projects with technical depth
            - Previous internship at top company or strong GitHub presence
            - Demonstrated algorithms/competitive programming skills
            - Clear leadership or mentoring experience

            This candidate should PASS a Big Tech internship screening. Use this as your baseline.
            """
        }

        prompt = f"""You are a resume screener at {config['company_type']} for a {role} position ({level_context}).

        {config['strictness']}

        {reference_examples.get(difficulty, reference_examples["easy"])}

        RESUME TO REVIEW:
        {text_content}

        INSTRUCTIONS:
        1. Compare this resume to the REFERENCE resume provided above
        2. The reference resume represents the MINIMUM bar for passing
        3. If this resume is EQUAL TO or BETTER THAN the reference, you should PASS them
        4. If this resume is WEAKER than the reference, you should REJECT them
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

        # Call Gemini API with retry logic
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = call_gemini_with_retry(
            client=client,
            model="gemini-2.5-flash",
            contents=prompt,
            max_retries=3,
            initial_delay=2
        )

        response_text = response.text

        # Parse response to determine if passed
        passed = "DECISION: PASS" in response_text.upper()

        return JSONResponse(content={
            "passed": passed,
            "feedback": response_text,
            "difficulty": difficulty,
            "role": role,
            "level": level
        })

    except HTTPException:
        raise
    except Exception as e:
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
            "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
            "difficulty": "Easy",
            "examples": [
                {"input": "nums = [2,7,11,15], target = 9", "output": "[0,1]", "explanation": "Because nums[0] + nums[1] == 9, we return [0, 1]."}
            ],
            "constraints": [
                "2 <= nums.length <= 10^4",
                "-10^9 <= nums[i] <= 10^9",
                "-10^9 <= target <= 10^9"
            ],
            "sampleTestCases": [
                {"input": {"nums": [2,7,11,15], "target": 9}, "expectedOutput": [0,1]},
                {"input": {"nums": [3,2,4], "target": 6}, "expectedOutput": [1,2]},
                {"input": {"nums": [3,3], "target": 6}, "expectedOutput": [0,1]}
            ],
            "hiddenTestCases": [
                {"input": {"nums": [1, 5, 3, 7, 9], "target": 10}, "expectedOutput": [2,3]},
                {"input": {"nums": [0, 4, 3, 0], "target": 0}, "expectedOutput": [0,3]},
                {"input": {"nums": [-1, -2, -3, -4, -5], "target": -8}, "expectedOutput": [2,4]},
                {"input": {"nums": [1, 2], "target": 3}, "expectedOutput": [0,1]},
                {"input": {"nums": [5, 75, 25], "target": 100}, "expectedOutput": [1,2]},
                {"input": {"nums": [1, 3, 4, 2], "target": 6}, "expectedOutput": [2,3]},
                {"input": {"nums": [10, 20, 30, 40, 50], "target": 90}, "expectedOutput": [3,4]},
                {"input": {"nums": [-3, 4, 3, 90], "target": 0}, "expectedOutput": [0,2]},
                {"input": {"nums": [1, 1, 1, 1, 1, 4, 1, 1, 1, 1, 1, 7, 1, 1, 1, 1, 1], "target": 11}, "expectedOutput": [5,11]}
            ]
        },
        {
            "id": "reverse-string",
            "title": "Reverse String",
            "description": "Write a function that reverses a string. The input string is given as an array of characters s.",
            "difficulty": "Easy",
            "examples": [
                {"input": "s = [\"h\",\"e\",\"l\",\"l\",\"o\"]", "output": "[\"o\",\"l\",\"l\",\"e\",\"h\"]"}
            ],
            "constraints": [
                "1 <= s.length <= 10^5",
                "s[i] is a printable ascii character"
            ],
            "sampleTestCases": [
                {"input": {"s": ["h","e","l","l","o"]}, "expectedOutput": ["o","l","l","e","h"]},
                {"input": {"s": ["H","a","n","n","a","h"]}, "expectedOutput": ["h","a","n","n","a","H"]}
            ],
            "hiddenTestCases": [
                {"input": {"s": ["a"]}, "expectedOutput": ["a"]},
                {"input": {"s": ["a","b"]}, "expectedOutput": ["b","a"]},
                {"input": {"s": ["A"," ","m","a","n",","," ","a"," ","p","l","a","n",","," ","a"," ","c","a","n","a","l",":"," ","P","a","n","a","m","a"]}, "expectedOutput": ["a","m","a","n","a","P"," ",":","l","a","n","a","c"," ","a"," ",",","n","a","l","p"," ","a"," ",",","n","a","m"," ","A"]},
                {"input": {"s": ["1","2","3","4","5"]}, "expectedOutput": ["5","4","3","2","1"]},
                {"input": {"s": ["!","@","#","$","%"]}, "expectedOutput": ["%","$","#","@","!"]},
                {"input": {"s": ["r","a","c","e","c","a","r"]}, "expectedOutput": ["r","a","c","e","c","a","r"]}
            ]
        }
    ],
    "medium": [
        {
            "id": "valid-parentheses",
            "title": "Valid Parentheses",
            "description": "Given a string s containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid.",
            "difficulty": "Medium",
            "examples": [
                {"input": "s = \"()\"", "output": "true"},
                {"input": "s = \"()[]{}\"", "output": "true"},
                {"input": "s = \"(]\"", "output": "false"}
            ],
            "constraints": [
                "1 <= s.length <= 10^4",
                "s consists of parentheses only '()[]{}'"
            ],
            "sampleTestCases": [
                {"input": {"s": "()"}, "expectedOutput": True},
                {"input": {"s": "()[]{}"}, "expectedOutput": True},
                {"input": {"s": "(]"}, "expectedOutput": False}
            ],
            "hiddenTestCases": [
                {"input": {"s": "{[]}"}, "expectedOutput": True},
                {"input": {"s": "([)]"}, "expectedOutput": False},
                {"input": {"s": "((()))"}, "expectedOutput": True},
                {"input": {"s": "())"}, "expectedOutput": False},
                {"input": {"s": "((("}, "expectedOutput": False},
                {"input": {"s": "{[()()]}"}, "expectedOutput": True},
                {"input": {"s": "()[]{}"}, "expectedOutput": True},
                {"input": {"s": "(([]){}"}, "expectedOutput": False}
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
                {"input": {"x": 9}, "expectedOutput": True}
            ]
        }
    ],
    "hard": [
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
                {"input": {"s": "abba"}, "expectedOutput": 2}
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
                {"input": {"intervals": [[2,3],[4,5],[6,7],[8,9],[1,10]]}, "expectedOutput": [[1,10]]}
            ]
        }
    ]
}


class TechnicalQuestionsRequest(BaseModel):
    company: str
    role: str
    difficulty: str

class RunCodeRequest(BaseModel):
    code: str
    question_id: str
    language: str = "python"  # python, javascript, java, cpp, c
    run_mode: str = "run"  # "run" for sample tests, "submit" for all tests

class VoiceInterviewRequest(BaseModel):
    company: str
    role: str

@app.post("/api/technical-questions")
async def get_technical_questions(request: TechnicalQuestionsRequest):
    """Get technical interview questions based on difficulty."""
    try:
        import random
        
        # Map job difficulty to question difficulty
        if request.difficulty == "easy":
            questions = TECHNICAL_QUESTIONS.get("easy", [])
            num_questions = 2
        elif request.difficulty == "medium":
            questions = TECHNICAL_QUESTIONS.get("medium", [])
            num_questions = 2
        elif request.difficulty == "hard":
            # For hard (FAANG), use 1 medium + 1 hard
            medium_q = TECHNICAL_QUESTIONS.get("medium", [])
            hard_q = TECHNICAL_QUESTIONS.get("hard", [])
            if medium_q and hard_q:
                selected_questions = [random.choice(medium_q), random.choice(hard_q)]
            else:
                selected_questions = hard_q if hard_q else medium_q
            return JSONResponse(content={
                "questions": selected_questions,
                "company": request.company,
                "role": request.role,
                "difficulty": request.difficulty
            })
        else:
            questions = TECHNICAL_QUESTIONS.get("easy", [])
            num_questions = 2

        # Randomize question selection
        if len(questions) > num_questions:
            selected_questions = random.sample(questions, num_questions)
        else:
            selected_questions = questions

        return JSONResponse(content={
            "questions": selected_questions,
            "company": request.company,
            "role": request.role,
            "difficulty": request.difficulty
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


def execute_python_code(code: str, test_input: dict, function_name: str = "solution") -> tuple[any, str]:
    """Execute Python code and return result and error message."""
    try:
        # Create a safe execution environment
        namespace = {"__builtins__": __builtins__}
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
        if "nums" in test_input and "target" in test_input:
            # Two Sum problem
            nums_copy = test_input["nums"].copy() if isinstance(test_input["nums"], list) else test_input["nums"]
            result = solution_func(nums_copy, test_input["target"])
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
    if (typeof solution === 'function') {{
        if (testInput.nums !== undefined && testInput.target !== undefined) {{
            result = solution(testInput.nums, testInput.target);
        }} else if (testInput.s !== undefined) {{
            result = solution(testInput.s);
        }} else {{
            result = solution(Object.values(testInput)[0]);
        }}
    }} else {{
        throw new Error('Solution function not found');
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


@app.post("/api/run-code")
async def run_code(request: RunCodeRequest):
    """Evaluate code against test cases with actual execution."""
    try:
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
            "reverse-string": "reverseString",
            "palindrome-number": "isPalindrome",
            "fizz-buzz": "fizzBuzz",
            "longest-substring": "lengthOfLongestSubstring",
            "valid-parentheses": "isValid",
            "group-anagrams": "groupAnagrams",
            "product-except-self": "productExceptSelf",
            "merge-intervals": "merge"
        }
        function_name = function_name_map.get(question["id"], "solution")

        print(f"Using function name: {function_name}")

        for idx, test_case in enumerate(test_cases):
            test_input = test_case["input"]
            expected_output = test_case["expectedOutput"]
            
            # Execute code based on language
            if request.language == "python":
                actual_output, error = execute_python_code(request.code, test_input, function_name)
            elif request.language == "javascript":
                actual_output, error = execute_javascript_code(request.code, test_input, function_name)
            else:
                # For other languages, use Python execution as fallback
                actual_output, error = execute_python_code(request.code, test_input, function_name)
            
            # Compare results
            passed = False
            if error:
                passed = False
                actual_output = None
            else:
                # Deep comparison of results
                passed = compare_outputs(actual_output, expected_output)

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

        # Calculate score
        score = (passed_count / total_tests) * 100 if total_tests > 0 else 0
        all_passed = passed_count == total_tests

        print(f"Final results: {passed_count}/{total_tests} passed, score={score}%")
        print(f"Test results array length: {len(test_results)}")

        return JSONResponse(content={
            "passed": all_passed,
            "score": round(score, 1),
            "passed_tests": passed_count,
            "total_tests": total_tests,
            "test_results": test_results
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred: {str(e)}"
        )


def compare_outputs(actual: any, expected: any) -> bool:
    """Compare actual and expected outputs, handling lists, nested structures."""
    import json
    
    # Handle None cases
    if actual is None and expected is None:
        return True
    if actual is None or expected is None:
        return False
    
    # Convert to comparable format
    try:
        # For lists/arrays, compare element-wise
        if isinstance(actual, list) and isinstance(expected, list):
            if len(actual) != len(expected):
                return False
            # Sort if order might differ (for some problems)
            # For most LeetCode problems, order matters, so don't sort
            return actual == expected
        
        # For primitive types
        return actual == expected
    except:
        # Fallback to string comparison
        return str(actual) == str(expected)


@app.post("/api/start-voice-interview")
async def start_voice_interview(request: VoiceInterviewRequest):
    """Start a voice interview session using ElevenLabs."""
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
        response = call_gemini_with_retry(
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
        
        # Generate audio for first question using ElevenLabs
        ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        audio_base64 = None
        
        if ELEVENLABS_API_KEY:
            try:
                headers = {
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json"
                }
                data = {
                    "text": first_question,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75
                    }
                }
                
                voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
                response = requests.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers=headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    audio_base64 = base64.b64encode(response.content).decode('utf-8')
                    print(f"ElevenLabs TTS success: Generated audio for question 1")
                else:
                    error_detail = response.text if response.text else "No error details"
                    print(f"ElevenLabs API error: {response.status_code} - {error_detail}")
                    if response.status_code == 401:
                        print("ElevenLabs authentication failed. Please check your API key or account quota.")
                    elif response.status_code == 429:
                        print("ElevenLabs rate limit exceeded. Please wait before making more requests.")
            except Exception as e:
                print(f"ElevenLabs error: {str(e)}")
        
        print(f"[DEBUG] Start interview response: question_number=1")
        return JSONResponse(content={
            "session_id": session_id,
            "first_question": first_question,
            "audio_base64": audio_base64,
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
        
        # Transcribe audio using Gemini's multimodal API or use Whisper
        # For now, using a simplified version - in production use Whisper API
        audio_content = await audio.read()
        
        # For actual transcription, you would use:
        # import openai
        # transcript = openai.Audio.transcribe("whisper-1", audio_file)
        # For now, mock transcription
        transcript = "This is a mock transcript of the candidate's response."
        
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
        eval_response = call_gemini_with_retry(
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
        response = call_gemini_with_retry(
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
        
        # Generate audio for response using ElevenLabs
        ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
        audio_base64 = None
        
        if ELEVENLABS_API_KEY:
            try:
                headers = {
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json"
                }
                data = {
                    "text": next_response,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75
                    }
                }
                
                voice_id = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice
                response = requests.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers=headers,
                    json=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    audio_base64 = base64.b64encode(response.content).decode('utf-8')
                    print(f"ElevenLabs TTS success: Generated audio")
                else:
                    error_detail = response.text if response.text else "No error details"
                    print(f"ElevenLabs API error: {response.status_code} - {error_detail}")
                    if response.status_code == 401:
                        print("ElevenLabs authentication failed. Please check your API key or account quota.")
                    elif response.status_code == 429:
                        print("ElevenLabs rate limit exceeded. Please wait before making more requests.")
            except Exception as e:
                print(f"ElevenLabs error: {str(e)}")
        
        print(f"[DEBUG] Returning question_number: {next_question_number}, completed: False")
        
        return JSONResponse(content={
            "next_question": next_response,
            "audio_base64": audio_base64,
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


async def evaluate_interview_performance(interview_state: dict, client: genai.Client) -> int:
    """
    Evaluate the candidate's performance based on the conversation history.
    Returns a score from 0-100.
    """
    try:
        # Extract conversation for evaluation
        conversation = interview_state.get("conversation_history", [])

        if not conversation:
            print("[Evaluation] No conversation history found, returning default score")
            return 50

        # Build conversation text
        conversation_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in conversation
        ])

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
    - If the candidate uses hateful/harassing language, threats, sexual content, or otherwise extremely unprofessional/offensive content, the overall_score must be severely reduced.
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

            # Hard caps for disqualifying content.
            if harassment_hate or sexual or violence_threat:
                score = min(score, 15)
            if unprofessional:
                score = min(score, 35)

            # Additional cap if any per-answer professionalism is extremely low.
            per = parsed.get("per_answer") if isinstance(parsed.get("per_answer"), list) else []
            try:
                min_prof = min(int(a.get("professionalism", 5)) for a in per if isinstance(a, dict)) if per else 5
                if min_prof <= 1:
                    score = min(score, 20)
            except Exception:
                pass

            print(f"[Evaluation] STAR score: {score} (flags={flags})")
            return score

        # If parsing fails, fall back conservatively (do not return a generous score).
        print(f"[Evaluation] Could not parse STAR JSON from: {raw[:200]}...")
        return 40

    except Exception as e:
        print(f"[Evaluation] Error evaluating performance: {str(e)}")
        import traceback
        traceback.print_exc()
        return 40  # Conservative fallback on error


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
        # Receive initial connection data (company, role)
        init_data = await websocket.receive_json()
        company = init_data.get("company", "a company")
        role = init_data.get("role", "a role")

        import uuid
        session_id = str(uuid.uuid4())

        print(f"[WebSocket] Starting behavioral interview for {role} at {company}")
        print(f"[WebSocket] Session ID: {session_id}")

        # Initialize interview session state
        interview_state = {
            "questions_asked": 0,
            "answers_completed": 0,
            "max_questions": 3,
            "questions": [],
            "scores": [],
            "conversation_history": [],
            "company": company,
            "role": role
        }

        # Configure Gemini Live API
        client = genai.Client(api_key=GEMINI_API_KEY)
        MODEL = "gemini-2.0-flash-exp"

        # Pre-generate canonical questions (clean UI text) using a non-Live model.
        # This avoids relying on output_audio_transcription, which can be garbled.
        try:
            questions_prompt = (
                f"Generate exactly 3 distinct behavioral interview questions for a {role} role at {company}.\n"
                "Each question must be 1-2 concise sentences, professional, and relevant to the role.\n"
                "Return STRICT JSON only, with this exact shape and no extra keys:\n"
                "{\"questions\": [\"...\", \"...\", \"...\"]}"
            )
            q_resp = await asyncio.to_thread(
                call_gemini_with_retry,
                client,
                "gemini-2.5-flash",
                questions_prompt,
                3,
                2,
            )
            parsed = json.loads((q_resp.text or "").strip())
            questions = parsed.get("questions") if isinstance(parsed, dict) else None
            if not isinstance(questions, list):
                raise ValueError("Invalid questions JSON")
            questions = [str(q).strip() for q in questions if str(q).strip()]
            if len(questions) != interview_state["max_questions"]:
                raise ValueError("Expected exactly 3 questions")
            interview_state["questions"] = questions
        except Exception as e:
            print(f"[WebSocket] Failed to pre-generate questions, using fallback: {e}")
            interview_state["questions"] = [
                "Tell me about a time you faced a challenging problem at work or school. What did you do and what was the outcome?",
                "Describe a time you had to work with a difficult teammate or resolve a conflict. How did you handle it?",
                "Tell me about a time you took initiative or led a project. What actions did you take and what did you learn?",
            ]

        # System instruction for the interview
        system_instruction = f"""You are a professional behavioral interviewer at {company} conducting an interview for a {role} position.

Your role:
1. You will be given the exact question text to ask.
2. Ask the question VERBATIM (no paraphrasing, no extra preamble).
3. Do NOT speak, acknowledge, or ask follow-ups unless you receive an explicit realtime text instruction.
4. After the candidate answers, remain silent until instructed.
5. After the final answer, deliver a brief closing remark ONLY when instructed.

Current question number: {interview_state['questions_asked'] + 1} of {interview_state['max_questions']}"""

        config = {
            # Note: Live API expects a single output modality. Requesting both
            # AUDIO and TEXT can cause a 1007 "invalid argument" during connect.
            "response_modalities": ["AUDIO"],
            # Ask Gemini to include transcripts alongside audio.
            "input_audio_transcription": {},
            "output_audio_transcription": {},
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": "Puck"
                    }
                }
            },
            "system_instruction": {
                "role": "system",
                "parts": [{"text": system_instruction}]
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

                    if acknowledge_first:
                        instruction = (
                            "Acknowledge the candidate briefly (1-2 sentences), then ask the following question exactly as written, with no extra words: "
                            + q_text
                        )
                    else:
                        instruction = (
                            "Ask the following question exactly as written, with no extra words: "
                            + q_text
                        )

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
                                                interview_state["conversation_history"].append({
                                                    "role": "candidate",
                                                    "content": user_text
                                                })
                                                print(f"[User] Response: {user_text[:100]}...")

                                                # Send transcript to frontend for display
                                                await websocket.send_json({
                                                    "type": "text",
                                                    "content": user_text,
                                                    "speaker": "candidate"
                                                })

                                # Handle server content (audio from Gemini)
                                if response.server_content:
                                    # Forward server-side transcriptions (works in AUDIO mode)
                                    if response.server_content.input_transcription and getattr(response.server_content.input_transcription, 'text', None):
                                        nonlocal_in = response.server_content.input_transcription.text
                                        in_transcript_local = _merge_transcript(in_transcript_local, nonlocal_in)
                                        now = time.monotonic()
                                        if now - last_in_sent >= 0.12 or getattr(response.server_content.input_transcription, 'finished', False):
                                            last_in_sent = now
                                            await websocket.send_json({
                                                "type": "text",
                                                "content": in_transcript_local,
                                                "speaker": "candidate"
                                            })
                                        if getattr(response.server_content.input_transcription, 'finished', False):
                                            interview_state["conversation_history"].append({
                                                "role": "candidate",
                                                "content": in_transcript_local
                                            })

                                    if response.server_content.output_transcription and getattr(response.server_content.output_transcription, 'text', None):
                                        # Intentionally ignored: output transcription is often garbled.
                                        # UI uses canonical questions instead.
                                        pass

                                    model_turn = response.server_content.model_turn
                                    if model_turn and model_turn.parts:
                                        for part in model_turn.parts:
                                            # Send audio data to frontend
                                            if hasattr(part, 'inline_data') and part.inline_data:
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

                                            # Also send text if model_turn includes it (rare in AUDIO mode)
                                            if hasattr(part, 'text') and part.text:
                                                text_content = part.text
                                                interview_state["conversation_history"].append({
                                                    "role": "interviewer",
                                                    "content": text_content
                                                })
                                                # Intentionally do not forward interviewer text to the UI.
                                                # Canonical questions are delivered via message.type == "question".
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
                                            final_score = await evaluate_interview_performance(interview_state, client)
                                            await websocket.send_json({
                                                "type": "interview_complete",
                                                "score": final_score
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
                                    await _send_canonical_question(next_q, acknowledge_first=True)
                                elif interview_state["answers_completed"] >= interview_state["max_questions"]:
                                    # After the 3rd response, ask Gemini to close.
                                    awaiting_close_turn_complete = True
                                    awaiting_question_turn_complete = False
                                    await session.send_realtime_input(
                                        text="Thank the candidate, provide a brief closing remark, and end the interview."
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
