@echo off
REM Ollama Dashboard Auto-Start Batch Script
REM This script checks if Ollama is running and starts/stops the dashboard accordingly

:monitor
echo Checking if Ollama is running...

tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
if %ERRORLEVEL% EQU 0 (
    REM Check if dashboard is already running
    tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I "wsgi.py">NUL
    if %ERRORLEVEL% EQU 0 (
        REM Dashboard is already running, continue monitoring
        goto wait
    ) else (
        echo Ollama is running. Starting dashboard...
        cd /d "%~dp0.."
        start "Ollama Dashboard" python wsgi.py
        echo Dashboard started. Monitoring for Ollama status...
    )
) else (
    REM Check if dashboard is running and stop it
    tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I "wsgi.py">NUL
    if %ERRORLEVEL% EQU 0 (
        echo Ollama stopped. Stopping dashboard...
        for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" ^| find /I "wsgi.py"') do (
            taskkill /PID %%i /F >nul 2>&1
        )
        echo Dashboard stopped.
    ) else (
        echo Ollama is not running. Please start Ollama first.
        echo You can start Ollama with: ollama serve
        echo.
        echo Press any key to start monitoring, or Ctrl+C to exit...
        pause >nul
    )
)

:wait
REM Wait 10 seconds before checking again
timeout /t 10 /nobreak >nul
goto monitor
