@echo off
echo Restarting Ollama Dashboard...
echo.

REM Stop the dashboard
echo [1/2] Stopping existing dashboard processes...
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr /C:"PID:"') do (
    for /f "tokens=*" %%j in ('wmic process where "ProcessId=%%i" get CommandLine /format:list ^| findstr /C:"OllamaDashboard.py"') do (
        echo Terminating process %%i...
        taskkill /PID %%i /F >nul 2>&1
        if errorlevel 1 (
            echo Warning: Could not stop process %%i
        ) else (
            echo Dashboard stopped successfully.
        )
    )
)

REM Wait a moment for processes to fully terminate
echo Waiting for processes to terminate...
timeout /t 2 /nobreak >nul

REM Start the dashboard
echo.
echo [2/2] Starting Ollama Dashboard...
IF EXIST .venv\Scripts\activate.bat (
    start "Ollama Dashboard" cmd /c ".venv\Scripts\activate.bat && python OllamaDashboard.py"
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
