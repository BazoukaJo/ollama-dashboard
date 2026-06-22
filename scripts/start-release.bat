@echo off
setlocal EnableDelayedExpansion
REM Release dashboard launcher — uses python -m waitress (not waitress-serve.exe) for App Control compatibility.
set "REPO=%~dp0.."
cd /d "%REPO%"

if not exist data mkdir data

if not exist .venv\Scripts\python.exe (
	echo Virtual environment not found! Please set up .venv first.
	exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO%\scripts\dashboard-process.ps1" -Action ensure-port -Mode release -RepoRoot "%REPO%"
set "ENSURE=!ERRORLEVEL!"
if "!ENSURE!"=="3" exit /b 0
if "!ENSURE!"=="2" exit /b 2
if not "!ENSURE!"=="0" exit /b !ENSURE!

echo release> data\dashboard.run-mode

set "PY=%REPO%\.venv\Scripts\python.exe"
set "RUNNER=%REPO%\scripts\run-release-server.bat"

powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO%\scripts\dashboard-process.ps1" -Action preflight -RepoRoot "%REPO%"
if errorlevel 1 (
	echo App preflight failed. Install dependencies: .venv\Scripts\pip install -r requirements.txt
	echo Details: data\dashboard-release-error.log
	exit /b 1
)

if /i "%~1"=="console" goto :foreground

echo %date% %time% Release dashboard starting (minimized, python -m waitress)...>> "%REPO%\data\dashboard-release-launch.log"

REM Empty title ("") required — otherwise START treats the next token as the window title/path.
start "" /min cmd /c call "%RUNNER%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO%\scripts\dashboard-process.ps1" -Action wait-ready -RepoRoot "%REPO%"
set "READY=!ERRORLEVEL!"
if "!READY!"=="2" (
	echo Cannot start: port 5000 is used by another application.
	exit /b 2
)
if not "!READY!"=="0" (
	echo Release dashboard did not become ready on port 5000.
	echo Check data\dashboard-release-error.log
	exit /b 1
)
exit /b 0

:foreground
call .venv\Scripts\activate.bat
set OLLAMA_DASHBOARD_CONFIG=production
echo.
echo Release server: http://127.0.0.1:5000
echo Logs: data\dashboard-release.log / data\dashboard-release-error.log
echo.
"%PY%" -m waitress --host=127.0.0.1 --port=5000 --threads=8 wsgi:app
set "RC=!ERRORLEVEL!"
exit /b !RC!
