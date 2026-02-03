@echo off
echo Starting Ollama Dashboard...
REM Activate the virtual environment if not already active
IF EXIST .venv312\Scripts\activate.bat (
	call .venv312\Scripts\activate.bat
	call python OllamaDashboard.py
) ELSE (
	echo Virtual environment not found! Please set up .venv312 first.
	exit /b 1
)
