@echo off
echo Starting Ollama Dashboard (production)...
REM Activate the virtual environment if not already active
IF EXIST .venv\Scripts\activate.bat (
	call .venv\Scripts\activate.bat
	call waitress-serve --call --host=0.0.0.0 --port=5000 --threads=8 app:create_app
) ELSE (
	echo Virtual environment not found! Please set up .venv first.
	pause
	exit /b 1
)