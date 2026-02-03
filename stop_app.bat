@echo off
echo Stopping Ollama Dashboard...

REM Find and kill Python processes running OllamaDashboard.py
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr /C:"PID:"') do (
    for /f "tokens=*" %%j in ('wmic process where "ProcessId=%%i" get CommandLine /format:list ^| findstr /C:"OllamaDashboard.py"') do (
        echo Terminating process %%i...
        taskkill /PID %%i /F >nul 2>&1
        if errorlevel 1 (
            echo Failed to stop process %%i
        ) else (
            echo Dashboard stopped successfully.
        )
    )
)

echo.
echo If the dashboard is still running, you may need to close it manually from Task Manager.
pause
