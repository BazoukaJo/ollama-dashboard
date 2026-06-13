@echo off

setlocal EnableDelayedExpansion

cd /d "%~dp0"

title Ollama Dashboard (release)

echo Starting Ollama Dashboard (release)...

IF NOT EXIST data mkdir data

echo release> data\dashboard.run-mode

IF NOT EXIST .venv\Scripts\activate.bat (

	echo Virtual environment not found! Please set up .venv first.

	pause

	exit /b 1

)

call .venv\Scripts\activate.bat

set OLLAMA_DASHBOARD_CONFIG=production

set FLASK_DEBUG=0

waitress-serve --host=127.0.0.1 --port=5000 --threads=8 wsgi:app

set EXITCODE=!ERRORLEVEL!

echo.

if !EXITCODE! neq 0 (

	echo Dashboard exited with error !EXITCODE!.

) else (

	echo Dashboard stopped.

)

pause

exit /b !EXITCODE!

