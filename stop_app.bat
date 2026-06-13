@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo Checking dashboard status...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action status
set "STATUS=!ERRORLEVEL!"

set "RUNMODE=unknown"
if exist data\dashboard.run-mode (
	set /p RUNMODE=<data\dashboard.run-mode
)

if "!STATUS!"=="0" (
	echo Stopping detected dashboard instance...
) else if "!STATUS!"=="4" (
	echo.
	echo Port 5000 is blocked by a non-dashboard process. Stop it manually, then retry.
	if /i not "%~1"=="--no-pause" pause
	exit /b 2
) else (
	echo No dashboard instance detected on port 5000.
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action stop
set "STOP=!ERRORLEVEL!"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action wait-clear
if not errorlevel 1 (
	echo Port 5000 is clear.
) else (
	echo Warning: port 5000 may still be in use.
)

if "!STOP!"=="1" (
	echo No dashboard instance was running.
) else if "!STOP!"=="0" (
	echo Dashboard stopped successfully.
) else if "!STOP!"=="2" (
	echo Stop refused: foreign process still owns port 5000.
	if /i not "%~1"=="--no-pause" pause
	exit /b 2
)

echo Last saved run mode: !RUNMODE!
echo.
if /i not "%~1"=="--no-pause" pause
endlocal
