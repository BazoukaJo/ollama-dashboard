To start Ollama Dashboard when Windows 11 starts:

1. Copy "Start Ollama Dashboard.bat" into the Startup folder.

   Windows 11 Startup folder (current user):
   
   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
   
   Full path:
   C:\Users\Admin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup

2. To open the folder quickly: press Win+R, paste:
   shell:startup
   then press Enter.

3. Paste (or drag) "Start Ollama Dashboard.bat" into that folder.

Done. The dashboard will start at login in the **background** (no staying console window).

Release logs: `data\dashboard-release-launch.log` and `data\dashboard-release-error.log` in the project folder.

To stop or restart later, use stop_app.bat or restart_app.bat in the project folder.
See docs\GUIDE.md (section "Windows: start, stop, and restart") for details.
