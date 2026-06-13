@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo Restarting Ollama Dashboard...
echo.

set "RUNMODE="

if /i "%~1"=="dev" (
	set "RUNMODE=dev"
) else if /i "%~1"=="release" (
	set "RUNMODE=release"
) else (
	for /f "usebackq delims=" %%M in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action resolve-mode`) do set "RUNMODE=%%M"
)

if not defined RUNMODE (
	if exist data\dashboard.run-mode (
		set /p RUNMODE=<data\dashboard.run-mode
	)
)
if /i not "!RUNMODE!"=="dev" set "RUNMODE=release"

echo Target run mode: !RUNMODE!
echo.

call "%~dp0stop_app.bat" --no-pause
if errorlevel 2 (
	echo Restart aborted: port 5000 is blocked by another application.
	pause
	exit /b 2
)

echo Waiting for port 5000 to clear...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action wait-clear
if errorlevel 1 (
	echo Warning: port 5000 may still be busy.
)

echo.
if /i "!RUNMODE!"=="dev" (
	echo [2/2] Starting development dashboard...
	IF EXIST .venv\Scripts\activate.bat (
		start "Ollama Dashboard (dev)" cmd /k pushd "%~dp0" ^&^& call start_dev.bat
	) ELSE (
		echo Virtual environment not found! Please set up .venv first.
		pause
		exit /b 1
	)
) ELSE (
	echo [2/2] Starting release dashboard...
	IF EXIST .venv\Scripts\activate.bat (
		start "Ollama Dashboard" cmd /k pushd "%~dp0" ^&^& call start.bat
	) ELSE (
		echo Virtual environment not found! Please set up .venv first.
		pause
		exit /b 1
	)
)

echo.
echo Dashboard is restarting in a new window.
echo You can close this window.
timeout /t 3 /nobreak >nul
endlocal
