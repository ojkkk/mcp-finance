@echo off
title mcp-finance Dashboard

echo ========================================
echo   mcp-finance Web Dashboard
echo ========================================
echo.

echo [1/2] Killing old processes...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8080" ^| find "LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
    echo   Killed PID %%a
)
timeout /t 2 /nobreak >nul

echo [2/2] Starting Flask server...
echo.
echo   Open http://localhost:8080
echo   Press Ctrl+C to stop
echo.

cd /d "%~dp0"
python -m mcp_finance.dashboard.app

pause
