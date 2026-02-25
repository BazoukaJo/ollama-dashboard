@echo off
echo Starting Ollama Dashboard...
REM Activate the virtual environment if not already active
IF EXIST .venv\Scripts\activate.bat (
	call .venv\Scripts\activate.bat
	call python OllamaDashboard.py
) ELSE (
	echo Virtual environment not found! Please set up .venv first.
	exit /b 1
)
`