@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo Restarting Ollama Dashboard...
echo.

set "RUNMODE="
set "NOPAUSE=0"
if /i "%OLLAMA_DASHBOARD_NO_PAUSE%"=="1" set "NOPAUSE=1"

for %%A in (%*) do (
	if /i "%%A"=="nopause" set "NOPAUSE=1"
	if /i "%%A"=="dev" set "RUNMODE=dev"
	if /i "%%A"=="release" set "RUNMODE=release"
)

if not defined RUNMODE (
	for /f "usebackq delims=" %%M in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action resolve-mode`) do set "RUNMODE=%%M"
)

if not defined RUNMODE (
	if exist data\dashboard.run-mode (
		set /p RUNMODE=<data\dashboard.run-mode
	)
)
if /i not "!RUNMODE!"=="dev" set "RUNMODE=release"

echo Target run mode: !RUNMODE!
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action stop -CloseLaunchers
set "STOP=!ERRORLEVEL!"
if "!STOP!"=="2" (
	echo Restart aborted: port 5000 is blocked by another application.
	if "!NOPAUSE!"=="0" pause
	exit /b 2
)
if "!STOP!"=="1" (
	echo No dashboard instance was running.
)
echo Waiting for port 5000 to clear...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dashboard-process.ps1" -Action wait-clear
if errorlevel 1 (
	echo Warning: port 5000 may still be busy.
)

echo.
if /i "!RUNMODE!"=="dev" (
	echo [2/2] Starting development dashboard...
	IF EXIST .venv\Scripts\activate.bat (
		start "Ollama Dashboard (dev)" cmd /k pushd "%~dp0" ^&^& call start_dev.bat
	) ELSE (
		echo Virtual environment not found! Please set up .venv first.
		if "!NOPAUSE!"=="0" pause
		exit /b 1
	)
) ELSE (
	echo [2/2] Starting release dashboard...
	IF EXIST .venv\Scripts\python.exe (
		call "%~dp0scripts\start-release.bat"
		if errorlevel 1 (
			echo Release start failed. Check data\dashboard-release-launch.log and data\dashboard-release-error.log
			if "!NOPAUSE!"=="0" pause
			exit /b 1
		)
	) ELSE (
		echo Virtual environment not found! Please set up .venv first.
		if "!NOPAUSE!"=="0" pause
		exit /b 1
	)
)

echo.
if /i "!RUNMODE!"=="dev" (
	echo Dashboard is restarting in a new development window.
) else (
	echo Release dashboard is restarting in the background.
)
endlocal
exit 0
