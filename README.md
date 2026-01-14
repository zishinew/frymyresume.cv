# OfferReady

[![Built with](https://img.shields.io/badge/Built_with-Google_Gemini-blue)](https://deepmind.google/technologies/gemini/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-blue)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue)](https://www.typescriptlang.org/)

**Master your job search with AI-powered resume reviews and realistic interview simulations.**

OfferReady is a comprehensive job preparation platform that helps you practice for real tech company interviews. Get instant feedback on your resume and experience the full application process from resume screening to behavioral interviews.

## ✨ Features

### Resume Review
* **Professional Analysis:** AI-powered resume evaluation
* **Role-Specific Feedback:** Tailored advice for your target position
* **Actionable Improvements:** Specific recommendations to strengthen your resume
* **File Support:** PDF and TXT formats accepted

### Job Application Simulator
* **Resume Screening:** Experience ruthlessly realistic screening by top tech companies
* **Company-Specific Evaluation:** Difficulty adjusted based on company tier (FAANG vs others)
* **Technical Interview:** (Coming soon) Coding challenges tailored to company standards
* **Behavioral Interview:** (Coming soon) AI voice interview using ElevenLabs
* **Full Pipeline:** Experience the complete hiring process from application to offer

### Modern Tech Stack
* **Clean UI:** Minimalist, modern design
* **Fast API:** Efficient FastAPI backend
* **Type-Safe:** Full TypeScript implementation
* **Responsive:** Works on all devices

---

## 🏗️ Architecture

This application consists of two parts:

1. **Backend**: FastAPI server that handles file uploads and AI analysis
2. **Frontend**: React + TypeScript interface for user interaction

---

## 💻 Local Development

### Prerequisites

* **Python 3.10+**
* **Node.js 18+** and npm
* **Google Gemini API Key**:
    1. Go to [Google AI Studio](https://aistudio.google.com/)
    2. Create a new API key
    3. Copy the key string

### Backend Setup

```bash
# Navigate to the project directory
cd Python/resume_critique

# Create a .env file and add your API key
echo "GEMINI_API_KEY=your_api_key_here" > .env

# Install Python dependencies (if using uv)
uv add fastapi uvicorn python-multipart google-genai python-dotenv PyPDF2

# Or with pip
pip install fastapi uvicorn python-multipart google-genai python-dotenv PyPDF2

# Run the backend server
python backend.py
```

The backend will start at `http://localhost:8000`

### Frontend Setup

```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies
npm install

# Run the development server
npm run dev
```

The frontend will start at `http://localhost:5173`

### Running Both Services

You'll need two terminal windows:

**Terminal 1 (Backend):**
```bash
cd Python/resume_critique
python backend.py
```

**Terminal 2 (Frontend):**
```bash
cd Python/resume_critique/frontend
npm run dev
```

Then open `http://localhost:5173` in your browser.

---

## 📁 Project Structure

```
resume_critique/
├── backend.py          # FastAPI backend server
├── main.py            # Original Streamlit app (legacy)
├── .env               # Environment variables (API keys)
├── requirements.txt   # Python dependencies
└── frontend/          # React + TypeScript frontend
    ├── src/
    │   ├── App.tsx    # Main application component
    │   ├── App.css    # Component styles
    │   └── index.css  # Global styles
    ├── package.json
    └── README.md
```

---

## 🚀 Deployment

### Backend Deployment

The FastAPI backend can be deployed to platforms like:
- Railway
- Render
- Heroku
- AWS/GCP/Azure

### Frontend Deployment

The React frontend can be deployed to:
- Vercel
- Netlify
- GitHub Pages

Make sure to update the API endpoint in [App.tsx](frontend/src/App.tsx) from `http://localhost:8000` to your production backend URL.

---

## 🛠️ API Documentation

Once the backend is running, visit `http://localhost:8000/docs` to see the interactive API documentation.

### Endpoints

- `GET /` - Health check
- `POST /api/analyze` - Analyze resume
  - Parameters:
    - `file`: Resume file (PDF or TXT)
    - `job_role`: Target job role (optional)
    - `notes`: Additional notes (optional)

---

## 🧪 Legacy Streamlit Version

The original Streamlit version is still available in [main.py](main.py). To run it:

```bash
streamlit run main.py
```

