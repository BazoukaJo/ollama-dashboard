@echo off

setlocal EnableDelayedExpansion

cd /d "%~dp0"



REM Release mode: minimized background window (App Control friendly).

REM Optional: start.bat console  — visible foreground server for troubleshooting.



IF NOT EXIST data mkdir data



IF NOT EXIST .venv\Scripts\python.exe (

	echo Virtual environment not found! Please set up .venv first.

	pause

	exit /b 1

)



if /i "%~1"=="console" (

	call "%~dp0scripts\start-release.bat" console

	set "RC=!ERRORLEVEL!"

	if "!RC!"=="0" exit /b 0

	if "!RC!"=="3" exit /b 0

	echo.

	if "!RC!"=="2" (

		echo Cannot start: port 5000 is used by another application.

	) else (

		echo Release start failed with exit code !RC!.

		echo Check data\dashboard-release-launch.log and data\dashboard-release-error.log

	)

	pause

	exit /b !RC!

)



call "%~dp0scripts\start-release.bat"

set "RC=!ERRORLEVEL!"

if "!RC!"=="0" exit /b 0

if "!RC!"=="3" exit /b 0

echo Release start failed with exit code !RC!.

echo Check data\dashboard-release-launch.log and data\dashboard-release-error.log

pause

exit /b !RC!

