# Ollama Dashboard - Application Restart Guide

This guide explains how to properly restart the Ollama Dashboard application.

## Quick Restart (Recommended)

### Using PowerShell Script (Windows)
```powershell
.\restart_app.ps1
```

### Using Batch File
```batch
.\start_app.bat
```
(Note: This only starts the app, doesn't stop existing instances)

## Manual Restart Process

### Step 1: Stop the Running Application

#### Option A: If running in a terminal window
- Press `Ctrl+C` in the terminal where the app is running
- Wait for the process to terminate

#### Option B: Find and kill the process
```powershell
# Find Python processes running the dashboard
Get-Process python* | Where-Object {
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
    $cmdLine -like "*ollama_dashboard*" -or $cmdLine -like "*wsgi*"
} | Stop-Process -Force
```

#### Option C: Kill process using port 5000
```powershell
# Find process using port 5000
$port = netstat -ano | findstr ":5000"
# Extract PID and kill it (replace <PID> with actual process ID)
Stop-Process -Id <PID> -Force
```

### Step 2: Verify Port is Free
```powershell
netstat -ano | findstr ":5000"
```
If nothing is returned, the port is free.

### Step 3: Start the Application

#### Option A: Using the main entry point
```powershell
# Activate virtual environment (if using one)
.\venv\Scripts\Activate.ps1

# Start the application
python ollama_dashboard.py
```

#### Option B: Using WSGI entry point
```powershell
python wsgi.py
```

#### Option C: Using the batch file
```batch
start_app.bat
```

#### Option D: Run in background (PowerShell)
```powershell
Start-Process python -ArgumentList "ollama_dashboard.py" -WorkingDirectory $PWD
```

## Development Mode Restart

For development with auto-reload (if using Flask's debug mode):

1. The app will auto-reload on code changes if started with:
   ```python
   app.run(host='0.0.0.0', port=5000, debug=True)
   ```

2. However, for configuration changes (like the fixes we just made), a full restart is required.

## Production Mode Restart

If running with Gunicorn or another WSGI server:

```powershell
# Stop Gunicorn
Get-Process gunicorn* | Stop-Process -Force

# Restart with Gunicorn
gunicorn wsgi:app --config docker/gunicorn.conf.py
```

## Verification

After restarting, verify the application is running:

1. **Check if port 5000 is listening:**
   ```powershell
   netstat -ano | findstr ":5000"
   ```

2. **Test the health endpoint:**
   ```powershell
   curl http://localhost:5000/api/health
   ```

3. **Open in browser:**
   Navigate to: http://localhost:5000

4. **Check logs:**
   ```powershell
   Get-Content logs\ollama-dashboard.log -Tail 20
   ```

## Troubleshooting

### Port Already in Use
If you get "Address already in use" error:
1. Find the process: `netstat -ano | findstr ":5000"`
2. Kill it: `Stop-Process -Id <PID> -Force`
3. Wait a few seconds
4. Try starting again

### Application Won't Start
1. Check Python version: `python --version` (should be 3.7+)
2. Verify dependencies: `pip list | findstr flask`
3. Check for errors in: `logs\ollama-dashboard.log`
4. Verify virtual environment is activated (if using one)

### Changes Not Reflecting
- Configuration changes require a full restart
- Code changes in Python files require a restart (unless using debug mode)
- Static files (CSS/JS) may need browser cache clear (Ctrl+F5)

## Environment Variables

If you need to set custom Ollama host/port:

```powershell
$env:OLLAMA_HOST = "localhost"
$env:OLLAMA_PORT = "11434"
python ollama_dashboard.py
```

Or set them permanently in your system environment variables.

