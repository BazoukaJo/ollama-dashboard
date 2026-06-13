@echo off

setlocal EnableDelayedExpansion

cd /d "%~dp0"

title Ollama Dashboard (development)

echo Starting Ollama Dashboard (development, debug)...

IF NOT EXIST data mkdir data

echo dev> data\dashboard.run-mode

IF NOT EXIST .venv\Scripts\activate.bat (

	echo Virtual environment not found! Please set up .venv first.

	pause

	exit /b 1

)

call .venv\Scripts\activate.bat

set OLLAMA_DASHBOARD_CONFIG=development

set FLASK_DEBUG=1

set FLASK_APP=app:create_app

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

