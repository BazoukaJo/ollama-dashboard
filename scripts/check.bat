@echo off
setlocal
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

python -m ruff check app tests scripts ollama_dashboard_cli.py
if errorlevel 1 exit /b 1

python -m pytest -q -m "not integration and not playwright" -n auto --dist loadscope
if errorlevel 1 exit /b 1

node tests\test_ask_message_format.js
if errorlevel 1 exit /b 1

echo All checks passed.
