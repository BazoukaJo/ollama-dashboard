# Ollama Dashboard Restart Script
# This script properly stops and restarts the Ollama Dashboard application

$ErrorActionPreference = "Stop"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Ollama Dashboard Restart Script" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# Step 1: Find and stop existing processes
Write-Host "Step 1: Checking for running instances..." -ForegroundColor Yellow

$processes = Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
    $cmdLine -like "*ollama_dashboard*" -or $cmdLine -like "*wsgi*" -or $cmdLine -like "*ollama-dashboard*"
}

if ($processes) {
    Write-Host "Found $($processes.Count) running process(es)" -ForegroundColor Yellow
    foreach ($proc in $processes) {
        Write-Host "  Stopping process PID: $($proc.Id) - $($proc.ProcessName)" -ForegroundColor Yellow
        try {
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            Write-Host "  ✓ Process stopped successfully" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ Error stopping process: $_" -ForegroundColor Red
        }
    }
    # Wait a moment for processes to fully terminate
    Start-Sleep -Seconds 2
} else {
    Write-Host "No running instances found" -ForegroundColor Green
}

# Step 2: Check if port 5000 is still in use
Write-Host ""
Write-Host "Step 2: Checking port 5000..." -ForegroundColor Yellow
$portInUse = netstat -ano | findstr ":5000"
if ($portInUse) {
    Write-Host "  Warning: Port 5000 is still in use" -ForegroundColor Yellow
    Write-Host "  You may need to wait a moment or manually free the port" -ForegroundColor Yellow
} else {
    Write-Host "  ✓ Port 5000 is available" -ForegroundColor Green
}

# Step 3: Activate virtual environment if it exists
Write-Host ""
Write-Host "Step 3: Setting up environment..." -ForegroundColor Yellow
$venvPath = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-Host "  Activating virtual environment..." -ForegroundColor Yellow
    & $venvPath
    Write-Host "  ✓ Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "  No virtual environment found, using system Python" -ForegroundColor Yellow
}

# Step 4: Start the application
Write-Host ""
Write-Host "Step 4: Starting Ollama Dashboard..." -ForegroundColor Yellow

$appPath = Join-Path $PSScriptRoot "ollama_dashboard.py"
if (-not (Test-Path $appPath)) {
    Write-Host "  ✗ Error: ollama_dashboard.py not found at $appPath" -ForegroundColor Red
    exit 1
}

Write-Host "  Starting application..." -ForegroundColor Yellow
Write-Host "  Dashboard will be available at: http://localhost:5000" -ForegroundColor Cyan
Write-Host ""

# Start the application in a new window so you can see the output
Start-Process python -ArgumentList $appPath -WorkingDirectory $PSScriptRoot -NoNewWindow

Write-Host "  ✓ Application started!" -ForegroundColor Green
Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Restart Complete!" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "The application is running in the background." -ForegroundColor Cyan
Write-Host "To view logs, check: logs\ollama-dashboard.log" -ForegroundColor Cyan
Write-Host "To stop the application, use Ctrl+C in the terminal or run:" -ForegroundColor Yellow
Write-Host "  Get-Process python* | Where-Object {...} | Stop-Process" -ForegroundColor Gray

