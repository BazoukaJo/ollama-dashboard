@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM Release mode: no visible terminal. Use start_dev.bat for development (visible console).
REM Optional: start.bat console  — visible launcher for troubleshooting.

IF NOT EXIST data mkdir data

IF NOT EXIST .venv\Scripts\waitress-serve.exe (
	echo Virtual environment not found! Please set up .venv first.
	pause
	exit /b 1
)

if /i "%~1"=="console" (
	powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch-release.ps1" -ShowConsole
	set "RC=!ERRORLEVEL!"
	if "!RC!"=="0" exit /b 0
	if "!RC!"=="3" exit /b 0
	echo.
	if "!RC!"=="2" (
		echo Cannot start: port 5000 is used by another application.
	) else (
		echo Release start failed with exit code !RC!.
		echo Check data\dashboard-release-launch.log
	)
	pause
	exit /b !RC!
)

wscript //nologo "%~dp0scripts\start-release-hidden.vbs"
exit /b 0
