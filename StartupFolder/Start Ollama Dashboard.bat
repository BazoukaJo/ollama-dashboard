@echo off
REM Paste this file (or a shortcut to it) in the Windows 11 Startup folder.
REM Startup folder path:
REM   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
REM Edit the cd path below if your repo is not at this location.
cd /d "C:\Users\Admin\OneDrive\Bureau\ollama-dashboard"
call scripts\start-release.bat
