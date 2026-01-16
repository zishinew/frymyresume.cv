#!/bin/bash

# Integration Script for Behavioral Interview V3
# This script helps integrate the new reliable interview system

set -e

echo "================================================"
echo "Behavioral Interview V3 Integration"
echo "================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "backend.py" ]; then
    echo "❌ Error: backend.py not found. Please run this script from the project root."
    exit 1
fi

echo "✅ Found backend.py"

# Create backup directory
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
echo "📦 Created backup directory: $BACKUP_DIR"

# Backup existing behavioral interview components
if [ -f "frontend/src/components/BehavioralInterviewLive.tsx" ]; then
    cp frontend/src/components/BehavioralInterviewLive.tsx "$BACKUP_DIR/"
    echo "✅ Backed up BehavioralInterviewLive.tsx"
fi

if [ -f "frontend/src/pages/JobSimulator.tsx" ]; then
    cp frontend/src/pages/JobSimulator.tsx "$BACKUP_DIR/"
    echo "✅ Backed up JobSimulator.tsx"
fi

echo ""
echo "================================================"
echo "Integration Steps"
echo "================================================"
echo ""

echo "Step 1: Add new WebSocket endpoint to backend.py"
echo "---"
echo "Add this code to your backend.py:"
echo ""
cat <<'EOF'
# Import the new handler (add at top of file)
from behavioral_interview_v3 import handle_behavioral_interview_websocket

# Add new WebSocket endpoint (add after existing endpoints)
@app.websocket("/ws/behavioral-interview-v3")
async def behavioral_interview_v3_websocket(websocket: WebSocket):
    """New reliable behavioral interview endpoint"""
    await handle_behavioral_interview_websocket(websocket, GEMINI_API_KEY)
EOF
echo ""

echo "Step 2: Update JobSimulator.tsx"
echo "---"
echo "Change line 9 from:"
echo "  import BehavioralInterviewLive from '../components/BehavioralInterviewLive'"
echo "To:"
echo "  import BehavioralInterviewV3 from '../components/BehavioralInterviewV3'"
echo ""
echo "And change line 949 from:"
echo "  <BehavioralInterviewLive"
echo "To:"
echo "  <BehavioralInterviewV3"
echo ""

echo "Step 3: Restart your development servers"
echo "---"
echo "Backend:  uvicorn backend:app --reload"
echo "Frontend: npm run dev (in frontend directory)"
echo ""

echo "================================================"
echo "Testing Checklist"
echo "================================================"
echo ""
echo "Test the following flow:"
echo "  1. Navigate to job selection"
echo "  2. Upload resume"
echo "  3. Pass technical interview (score >= 80%)"
echo "  4. Start behavioral interview"
echo "  5. Answer all 3 questions"
echo "  6. Verify evaluation completes"
echo "  7. Check final score"
echo ""

echo "================================================"
echo "Quick Test Commands"
echo "================================================"
echo ""
echo "# Terminal 1 - Start backend"
echo "cd $(pwd)"
echo "python backend.py"
echo ""
echo "# Terminal 2 - Start frontend"
echo "cd $(pwd)/frontend"
echo "npm run dev"
echo ""

echo "================================================"
echo "Rollback Instructions (if needed)"
echo "================================================"
echo ""
echo "If you need to rollback:"
echo "  cp $BACKUP_DIR/BehavioralInterviewLive.tsx frontend/src/components/"
echo "  cp $BACKUP_DIR/JobSimulator.tsx frontend/src/pages/"
echo "  # Remove the import line from backend.py"
echo "  # Remove the @app.websocket(\"/ws/behavioral-interview-v3\") endpoint"
echo ""

echo "================================================"
echo "Documentation"
echo "================================================"
echo ""
echo "Full documentation: BEHAVIORAL_INTERVIEW_V3_README.md"
echo ""

echo "✅ Backup complete. Ready for integration!"
echo ""
echo "Read BEHAVIORAL_INTERVIEW_V3_README.md for detailed instructions."
