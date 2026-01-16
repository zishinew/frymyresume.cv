# frymyresume.cv

[![Built with](https://img.shields.io/badge/Built_with-Google_Gemini-blue)](https://deepmind.google/technologies/gemini/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-blue)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue)](https://www.typescriptlang.org/)

**AI-powered resume critique + a full internship interview pipeline (screening → technical → behavioral).**

frymyresume.cv helps you stress‑test your resume, simulate realistic internship hiring rounds, and practice live behavioral interviews with audio + speech‑to‑text.

## ✨ What’s New / Key Features

### Resume Review
- **AI critique + score** with targeted, role‑specific feedback
- **Actionable recommendations** grouped into clear sections
- **PDF/TXT support** with client‑side file validation

### Job Application Simulator (End‑to‑End)
- **Preset jobs** (curated internship roles with difficulty tiers)
- **Real internships** from SimplifyJobs (search + filter)
- **Resume screening** calibrated by internship difficulty
- **Auto‑inferred difficulty** for real listings (AI‑based)

### Real Job Details (Optional)
- **Job posting summarization** (paraphrased) from apply links
- **Requirements + responsibilities** extracted into structured bullets

### Technical Interview
- **Timed coding round** with Monaco editor
- **Multiple languages**: Python, JavaScript, Java, C++, C
- **Run vs submit** (sample vs hidden tests)
- **Auto‑grading + efficiency checks** (with penalties for sub‑optimal solutions)

### Live Behavioral Interview
- **Real‑time WebSocket interview** using Gemini Live audio
- **Speech‑to‑text** via Web Speech API (Chrome recommended)
- **Scoring + disqualification guardrails** for unprofessional responses

---

## 🏗️ Architecture

1. **Backend**: FastAPI server for AI analysis, screening, grading, and job scraping
2. **Frontend**: React + TypeScript single‑page app

---

## 💻 Local Development

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** and npm
- **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com/)

### Environment Variables

Create a .env file in this folder:

```
GEMINI_API_KEY=your_gemini_api_key_here
```

Optional (legacy voice endpoint):

```
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
```

### Install Dependencies

```bash
# Backend
pip install -r requirements-backend.txt

# Frontend
cd frontend
npm install
```

### Run Dev Servers

**Option A (one command):**

```bash
./run_dev.sh
```

**Option B (two terminals):**

```bash
# Terminal 1
python backend.py
```

```bash
# Terminal 2
cd frontend
npm run dev
```

Frontend: `http://localhost:5173`
Backend: `http://localhost:8000`
API Docs: `http://localhost:8000/docs`

---

## 📁 Project Structure (High‑Level)

```
resume_critique/
├── backend.py
├── run_dev.sh
├── requirements-backend.txt
├── data/
├── frontend/
│   ├── src/
│   │   ├── pages/        # Landing, ResumeReview, JobSimulator
│   │   ├── components/   # Technical + Behavioral interviews
│   │   └── lib/          # Speech-to-text helpers
│   └── public/
└── vercel.json
```

---

## 🛠️ API Surface (Backend)

### Resume
- `POST /api/analyze` — Resume critique + score

### Job Simulator
- `POST /api/screen-resume` — Resume screening
- `GET /api/jobs/real` — Real internship listings (SimplifyJobs)
- `GET /api/jobs/real/details` — Summarized job details

### Technical Interview
- `POST /api/technical-questions` — Get interview questions
- `POST /api/run-code` — Run/submit solution against tests
- `POST /api/technical/problem` — Generate original problem prompt + tests
- `POST /api/technical/grade` — Grade against generated session

### Behavioral Interview
- `WS /ws/behavioral-interview` — Live voice interview (Gemini Live)

### Legacy Voice Endpoints
- `POST /api/start-voice-interview`
- `POST /api/voice-response`

---

## 🚀 Deployment Notes

- **Backend**: Railway / Render / Fly.io / Docker
- **Frontend**: Vercel / Netlify
- Update API endpoints in `frontend/src/config.ts` for production.
- Lock down CORS origins in `backend.py` when deploying.

---

## ⚠️ Notes & Limitations

- **Behavioral interview** works best in Chrome (Web Speech API).
- Some **real job postings** block scraping; those details may be unavailable.

---

## 🧪 Legacy Streamlit Version

The original Streamlit app is still available in `main.py`:

```bash
streamlit run main.py
```

