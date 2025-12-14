#!/bin/bash
set -e

# Start the FastAPI server in the background
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Start the LiveKit agent
python app/livekit/agent.py start
