@echo off
REM Waitress server worker — started minimized by scripts\start-release.bat
setlocal
set "REPO=%~dp0.."
cd /d "%REPO%"
if not exist data mkdir data
set OLLAMA_DASHBOARD_CONFIG=production
"%REPO%\.venv\Scripts\python.exe" -m waitress --host=127.0.0.1 --port=5000 --threads=8 wsgi:app >> "%REPO%\data\dashboard-release.log" 2>> "%REPO%\data\dashboard-release-error.log"
