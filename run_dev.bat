@echo off
echo =================================━━━━━━━━━━━━━━━━━━━━━━━━━
echo   Starting LearnForge AI Local Development Servers...
echo =================================━━━━━━━━━━━━━━━━━━━━━━━━━

start "FastAPI Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --app-dir src/backend --reload --host 127.0.0.1 --port 8000"
start "Vite Frontend" cmd /k "npm run dev"

echo.
echo   FastAPI Backend : http://localhost:8000/
echo   Vite Frontend   : http://localhost:5173/
echo.
