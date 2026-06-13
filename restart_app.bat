@echo off
cd /d "%~dp0"
echo Restarting Ollama Dashboard...
echo.

set "RUNMODE=release"
if exist data\dashboard.run-mode (
	set /p RUNMODE=<data\dashboard.run-mode
)

echo Last run mode: %RUNMODE%
echo.

REM Stop (reuse stop script without pause)
call "%~dp0stop_app.bat" --no-pause

REM Wait for port to clear
echo Waiting for processes to terminate...
timeout /t 2 /nobreak >nul

echo.
if /i "%RUNMODE%"=="dev" (
	echo [2/2] Starting Ollama Dashboard (development, debug)...
	IF EXIST .venv\Scripts\activate.bat (
		start "Ollama Dashboard (dev)" cmd /k pushd "%~dp0" ^&^& call start_dev.bat
	) ELSE (
		echo Virtual environment not found! Please set up .venv first.
		pause
		exit /b 1
	)
) ELSE (
	echo [2/2] Starting Ollama Dashboard (release)...
	IF EXIST .venv\Scripts\activate.bat (
		start "Ollama Dashboard" cmd /k pushd "%~dp0" ^&^& call start.bat
	) ELSE (
		echo Virtual environment not found! Please set up .venv first.
		pause
		exit /b 1
	)
)

echo.
echo Dashboard is restarting in a new window...
echo You can close this window.
timeout /t 3 /nobreak >nul
