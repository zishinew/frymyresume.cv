# Quick Setup Guide

This guide will help you get the React + TypeScript frontend and FastAPI backend running.

## Prerequisites

1. **Python 3.10+** installed
2. **Node.js 18+** and npm installed
3. **Google Gemini API Key** (get one from [Google AI Studio](https://aistudio.google.com/))

## Quick Start

### 1. Setup Environment

```bash
# Create .env file with your API key
echo "GEMINI_API_KEY=your_api_key_here" > .env
```

### 2. Install Backend Dependencies

```bash
# Using pip
pip install -r requirements-backend.txt

# Or using uv (if installed)
uv pip install -r requirements-backend.txt
```

### 3. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. Run Development Servers

**Option A: Use the convenience script (Unix/Mac/Linux)**

```bash
./run_dev.sh
```

**Option B: Run manually (all platforms)**

Open two terminal windows:

Terminal 1 - Backend:
```bash
python backend.py
```

Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

### 5. Open the Application

Navigate to `http://localhost:5173` in your browser.

## Testing the Application

1. Upload a resume (PDF or TXT format)
2. Optionally enter a target job role (e.g., "Software Engineer")
3. Optionally add notes
4. Click "Analyze Resume!"
5. Wait for AI-powered feedback

## API Documentation

View the interactive API docs at `http://localhost:8000/docs` when the backend is running.

## Troubleshooting

### Backend won't start
- Check that your GEMINI_API_KEY is set correctly in `.env`
- Ensure all Python dependencies are installed
- Make sure port 8000 is not already in use

### Frontend won't start
- Ensure all npm dependencies are installed (`npm install`)
- Make sure port 5173 is not already in use

### CORS errors
- Make sure the backend is running on `http://localhost:8000`
- Check that CORS is properly configured in [backend.py](backend.py)

### File upload not working
- Ensure the file is PDF or TXT format
- Check that the file size is reasonable (< 10MB recommended)
- Look at browser console and backend logs for errors

## Development Tips

- The frontend uses hot module replacement (HMR) - changes will reflect immediately
- The backend uses Uvicorn which auto-reloads on code changes
- Check browser DevTools Console for frontend errors
- Check terminal output for backend errors
- Use the `/docs` endpoint to test API endpoints directly

## Building for Production

### Frontend

```bash
cd frontend
npm run build
```

The production build will be in `frontend/dist/`

### Backend

The backend is production-ready when using Uvicorn with proper configuration:

```bash
uvicorn backend:app --host 0.0.0.0 --port 8000 --workers 4
```

Remember to:
- Set environment variables properly in production
- Update CORS origins in [backend.py](backend.py) to match your frontend domain
- Use a production-grade web server (nginx, Caddy) as a reverse proxy
- Enable HTTPS
