# Gemini Live API Integration - Setup Guide

## Overview

Your behavioral interview now uses Google Gemini Live API for real-time, bidirectional voice conversations. This eliminates the need for ElevenLabs and provides a much better interview experience.

## What Changed

### Backend ([backend.py](backend.py))
- **New WebSocket endpoint**: `/ws/behavioral-interview`
- **Gemini Live API integration**: Real-time audio streaming
- **Server-to-server architecture**: Your FastAPI backend acts as a proxy between frontend and Gemini

### Frontend
- **New component**: `BehavioralInterviewLive.tsx` - WebSocket-based real-time audio
- **JobSimulator updated**: Now uses the Live version instead of the old component
- **Real-time streaming**: Continuous audio input/output instead of chunked recording

## Architecture

```
Frontend (React) <--> WebSocket <--> FastAPI Backend <--> WebSocket <--> Gemini Live API
     |                                       |
  Browser mic                        Session management
  Audio playback                     Scoring & tracking
```

## How It Works

1. **Connection**: Frontend opens WebSocket to backend, backend opens WebSocket to Gemini Live API
2. **Audio Streaming**:
   - User speaks → Browser captures audio → Sent to backend → Forwarded to Gemini
   - Gemini responds → Backend receives audio → Forwarded to frontend → Played in browser
3. **State Management**: Backend tracks questions asked, manages interview flow, calculates scores
4. **Completion**: After 3 questions, backend sends final score to frontend

## Setup Instructions

### 1. Verify Dependencies

All required packages should already be installed:
- `google-genai` (v1.50.1) ✓
- `websockets` (v15.0.1) ✓
- `fastapi` with WebSocket support ✓

### 2. API Key

Your `GEMINI_API_KEY` in `.env` will be used for Gemini Live API access. No additional setup needed!

### 3. Model Information

The backend uses: `gemini-2.0-flash-exp`
- This is the experimental Gemini 2.0 model with native audio support
- Supports real-time bidirectional audio streaming
- Uses "Puck" voice by default (you can change this in backend.py line 1349)

## Testing the Integration

### Step 1: Start Backend

```bash
cd /Users/zishine/VSCODE/Python/resume_critique
source .venv/bin/activate
python backend.py
```

You should see:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 2: Start Frontend

In a new terminal:
```bash
cd /Users/zishine/VSCODE/Python/resume_critique/frontend
npm run dev
```

### Step 3: Test the Interview

1. Navigate to the Job Simulator
2. Select a job and upload your resume
3. Pass the resume screening and technical interview
4. When you reach the behavioral interview stage:
   - **Click "Start Speaking"** when you're ready to answer
   - **Speak naturally** - the AI will hear you in real-time
   - **Click "Stop Speaking"** when you finish your answer
   - Wait for the AI to respond with the next question
   - Repeat for 3 questions

## Audio Configuration

### Input (Your voice):
- **Sample Rate**: 16kHz
- **Format**: 16-bit PCM mono
- **Echo Cancellation**: Enabled
- **Noise Suppression**: Enabled

### Output (Gemini's voice):
- **Sample Rate**: 24kHz
- **Format**: PCM (decoded automatically)
- **Voice**: Puck (can be changed to other voices)

## Troubleshooting

### Issue: "Connection error occurred"
- **Solution**: Make sure backend is running on port 8000
- Check: `curl http://localhost:8000/` should return API info

### Issue: "Failed to access microphone"
- **Solution**: Grant microphone permissions in your browser
- Chrome: Click the lock icon in address bar → Site settings → Microphone

### Issue: Gemini API errors in backend console
- **Check API key**: Verify `GEMINI_API_KEY` in `.env` is valid
- **Check quota**: Gemini Live API is in preview, check your quota at https://aistudio.google.com

### Issue: Audio quality is poor
- **Use headphones**: This prevents echo and feedback
- **Check microphone**: Use a good quality mic for best results
- **Network**: Ensure stable internet connection

## Advanced Configuration

### Change AI Voice

Edit `backend.py` line 1334:
```python
"voice_name": "Puck"  # Options: Puck, Charon, Kore, Fenrir, Aoede
```

### Adjust Question Count

Edit `backend.py` line 1304:
```python
"max_questions": 3,  # Change to desired number
```

### Customize System Instructions

Edit the system_instruction in `backend.py` lines 1316-1326 to modify:
- Interview style
- Question types
- Interview flow
- Response format

### Modify Scoring Criteria

The evaluation function is at lines 1299-1403. You can adjust:
- **Scoring weights**: Change the point distribution for each criterion
- **Scoring guidelines**: Modify the score ranges and descriptions
- **Evaluation model**: Currently uses `gemini-2.0-flash-exp`, can be changed

## API Costs

Gemini Live API pricing (as of Jan 2025):
- **Free tier**: Available during preview
- **Input audio**: Processed in real-time
- **Output audio**: Generated in real-time

Check current pricing at: https://ai.google.dev/pricing

## Reverting to Old Version

If you need to revert to the old ElevenLabs-based version:

1. Edit `frontend/src/pages/JobSimulator.tsx` line 7-8:
```typescript
import BehavioralInterview from '../components/BehavioralInterview'
// import BehavioralInterviewLive from '../components/BehavioralInterviewLive'
```

2. Edit line 399:
```typescript
<BehavioralInterview
  company={applicationData.selectedJob.company}
  role={applicationData.selectedJob.role}
  onComplete={handleBehavioralComplete}
/>
```

## Scoring System

The interview now includes **real-time AI evaluation** of candidate responses!

### How It Works

1. **Conversation Tracking**: All questions and responses are captured with transcripts
2. **Post-Interview Evaluation**: After 3 questions, Gemini analyzes the full conversation
3. **Comprehensive Scoring**: Evaluates based on 4 weighted criteria (25 points each):
   - Communication & Clarity
   - Relevance & Specificity
   - Problem-Solving & Critical Thinking
   - Leadership & Teamwork

### Score Ranges

- **90-100**: Exceptional (FAANG-level)
- **75-89**: Strong (ready for top companies)
- **60-74**: Good (solid performance)
- **45-59**: Fair (needs improvement)
- **0-44**: Weak (significant gaps)

### Real-Time Transcripts

The UI now shows:
- **Interviewer questions** (displayed as they're asked)
- **Your responses** (what Gemini heard you say)
- Live feedback on transcription accuracy

## Next Steps

1. **Test the integration** - Run through a full interview
2. **Customize prompts** - Adjust system instructions for your use case
3. **Add features**: Consider adding:
   - Interview recording/playback
   - Detailed feedback per question
   - Custom question pools by role
   - Multi-language support

## Resources

- [Gemini Live API Docs](https://ai.google.dev/gemini-api/docs/live)
- [WebSocket Reference](https://ai.google.dev/api/live)
- [Voice Options](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/multimodal-live#voice-names)

## Support

If you encounter issues:
1. Check backend logs for detailed error messages
2. Check browser console for frontend errors
3. Verify WebSocket connection is established
4. Test your Gemini API key with a simple request

Happy interviewing! 🎤🤖
