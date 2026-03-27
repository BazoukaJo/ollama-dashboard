@echo off
echo Restarting Ollama Dashboard...
echo.

REM Stop the dashboard by killing the process on port 5000
echo [1/2] Stopping existing dashboard processes...
set "found=0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    echo Terminating process %%a...
    taskkill /PID %%a /F >nul 2>&1
    if errorlevel 1 (
        echo Warning: Could not stop process %%a
    ) else (
        echo Dashboard stopped successfully.
        set "found=1"
    )
)

if "%found%"=="0" (
    echo No running dashboard found on port 5000.
)

REM Wait a moment for processes to fully terminate
echo Waiting for processes to terminate...
timeout /t 2 /nobreak >nul

REM Start the dashboard
echo.
echo [2/2] Starting Ollama Dashboard (production)...
IF EXIST .venv\Scripts\activate.bat (
    start "Ollama Dashboard" cmd /c ".venv\Scripts\activate.bat && waitress-serve --call --host=127.0.0.1 --port=5000 --threads=8 app:create_app"
    echo.
    echo Dashboard is restarting in a new window...
    echo You can close this window.
) ELSE (
    echo Virtual environment not found! Please set up .venv first.
    pause
    exit /b 1
)

echo.
echo Restart complete!
timeout /t 3 /nobreak >nul
