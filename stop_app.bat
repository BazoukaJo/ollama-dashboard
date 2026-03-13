@echo off
echo Stopping Ollama Dashboard...

REM Find and kill the process listening on port 5000
set "found=0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    echo Terminating process %%a...
    taskkill /PID %%a /F >nul 2>&1
    if errorlevel 1 (
        echo Failed to stop process %%a
    ) else (
        echo Dashboard stopped successfully.
        set "found=1"
    )
)

if "%found%"=="0" (
    echo No running dashboard found on port 5000.
)

echo.
echo If the dashboard is still running, you may need to close it manually from Task Manager.
pause
