#!/usr/bin/env bash
# Start the BuildAdvisor Flask backend and Streamlit frontend together.
# Usage: ./run.sh   (Ctrl+C stops both)
set -e
cd "$(dirname "$0")"

echo "Starting Flask backend on http://localhost:8000 ..."
python backend.py &
BACKEND_PID=$!

# Stop the backend when this script exits.
trap "echo; echo 'Stopping backend...'; kill $BACKEND_PID 2>/dev/null" EXIT

sleep 2
echo "Starting Streamlit frontend on http://localhost:8501 ..."
streamlit run app.py
