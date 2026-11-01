# CivicGuard Autopilot Launch Script
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  CivicGuard Autopilot - Control Plane Starting...  " -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

Start-Process "http://127.0.0.1:8000"

if (Test-Path "$ScriptDir\.python\python.exe") {
    Write-Host "[OK] Using bundled environment..." -ForegroundColor Green
    & "$ScriptDir\.python\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
} else {
    Write-Host "[OK] Using system Python..." -ForegroundColor Green
    python run.py
}

