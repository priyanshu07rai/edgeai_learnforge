#!/bin/bash

# LearnForge AI — Startup Script
# Boots up both the FastAPI python backend and serve the built Vite production frontend.

# Color formatting
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}======================================================================${NC}"
echo -e "${GREEN}                     Starting LearnForge AI                           ${NC}"
echo -e "${BLUE}======================================================================${NC}"

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment '.venv' not found. Please run ./deploy.sh first."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Add backend directory to PYTHONPATH
export PYTHONPATH=src/backend

# Clean up function to terminate background processes on exit
cleanup() {
    echo -e "\nShutting down servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}
trap cleanup SIGINT SIGTERM EXIT

# Start FastAPI backend
echo -e "Starting FastAPI Backend server..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start Vite production preview server
echo -e "Starting Vite Production Frontend server..."
npm run preview -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

# Wait for both servers
echo -e "${GREEN}LearnForge AI is up and running!${NC}"
echo -e "Access the frontend at: ${GREEN}http://localhost:5173${NC} (or your Jetson's local IP)"
echo -e "Access the backend APIs at: ${GREEN}http://localhost:8000${NC}"
echo -e "Press Ctrl+C to stop both servers."
wait
