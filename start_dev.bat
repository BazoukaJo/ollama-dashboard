@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title Ollama Dashboard (development)

echo Starting Ollama Dashboard (development, debug)...

IF NOT EXIST data mkdir data

IF NOT EXIST .venv\Scripts\activate.bat (
	echo Virtual environment not found! Please set up .venv first.
	pause
	exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action ensure-port -Mode dev
set "ENSURE=!ERRORLEVEL!"
if "!ENSURE!"=="3" (
	echo.
	echo Development dashboard is already running. Use stop_app.bat to stop it, or restart_app.bat to restart.
	pause
	exit /b 0
)
if "!ENSURE!"=="2" (
	echo.
	echo Cannot start: port 5000 is used by another application.
	pause
	exit /b 1
)
if not "!ENSURE!"=="0" (
	echo.
	echo Could not free port 5000 for the development dashboard.
	pause
	exit /b 1
)

echo dev> data\dashboard.run-mode

call .venv\Scripts\activate.bat

set OLLAMA_DASHBOARD_CONFIG=development
set FLASK_DEBUG=1
set FLASK_APP=app:create_app

echo.
echo Development server: http://127.0.0.1:5000
echo.

python -m flask run --host=127.0.0.1 --port=5000 --debug

set EXITCODE=!ERRORLEVEL!

echo.
if !EXITCODE! neq 0 (
	echo Dashboard exited with error !EXITCODE!.
) else (
	echo Dashboard stopped.
)

pause
exit /b !EXITCODE!
