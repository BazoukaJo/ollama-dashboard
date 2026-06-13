@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "RUNMODE=unknown"
if exist data\dashboard.run-mode (
	set /p RUNMODE=<data\dashboard.run-mode
)
echo Stopping Ollama Dashboard (mode: !RUNMODE!)...

set "found=0"

REM Kill every process tree listening on port 5000 (Waitress, Flask child, etc.)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr /R /C:":5000 .*LISTENING"') do (
	if not "%%a"=="0" (
		echo Terminating process tree %%a...
		taskkill /PID %%a /T /F >nul 2>&1
		if not errorlevel 1 set "found=1"
	)
)

REM Flask debug reloader parent and other dashboard launchers (not always on :5000)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
	"$killed = $false; try { Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue; $killed = $true }; Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'flask run|waitress-serve|ollama_dashboard_cli|OllamaDashboard\.py|wsgi:app') -and ($_.CommandLine -match '5000|create_app|wsgi') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $killed = $true }; if ($killed) { exit 0 } else { exit 1 } } catch { exit 1 }"

if not errorlevel 1 set "found=1"

if "!found!"=="0" (
	echo No running dashboard found on port 5000.
) else (
	echo Dashboard stopped successfully.
)

echo.
echo If the dashboard is still running, you may need to close it manually from Task Manager.
if /i not "%~1"=="--no-pause" pause
endlocal
