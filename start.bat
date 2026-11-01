@echo off
title CivicGuard Autopilot
echo ===================================================
echo   CivicGuard Autopilot - Control Plane Starting...
echo ===================================================
cd /d "%~dp0"

if exist ".python\python.exe" (
    echo [OK] Using bundled portable Python environment...
    start http://127.0.0.1:8000
    ".python\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
) else (
    echo [OK] Using system Python...
    start http://127.0.0.1:8000
    python run.py
)

pause

