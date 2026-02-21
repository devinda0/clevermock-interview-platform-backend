#!/bin/bash
set -e

# Start the FastAPI server
# In K8s, the agent is run as a separate deployment, so we shouldn't start it here.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
