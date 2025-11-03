# Ollama Dashboard Auto-Start Script
# This script checks if Ollama is running and starts the dashboard automatically

param(
    [switch]$Monitor,
    [int]$CheckInterval = 10
)

$ErrorActionPreference = "Stop"

# Configuration
$DASHBOARD_DIR = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$OLLAMA_PROCESS_NAME = "ollama"

function Test-OllamaRunning {
    try {
        $ollamaProcess = Get-Process -Name $OLLAMA_PROCESS_NAME -ErrorAction SilentlyContinue
        return $null -ne $ollamaProcess
    }
    catch {
        return $false
    }
}

function Start-Dashboard {
    Write-Host "Starting Ollama Dashboard..." -ForegroundColor Green

    try {
        Push-Location $DASHBOARD_DIR
        $process = Start-Process -FilePath "python" -ArgumentList "wsgi.py" -WorkingDirectory $DASHBOARD_DIR -NoNewWindow -PassThru
        Write-Host "Dashboard started successfully (PID: $($process.Id))" -ForegroundColor Green
        return $process
    }
    catch {
        Write-Error "Failed to start dashboard: $_"
        return $null
    }
    finally {
        Pop-Location
    }
}

function Stop-Dashboard {
    try {
        $pythonProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*wsgi.py*" }
        foreach ($process in $pythonProcesses) {
            Write-Host "Stopping dashboard process (PID: $($process.Id))..." -ForegroundColor Yellow
            Stop-Process -Id $process.Id -Force
        }
    }
    catch {
        Write-Warning "Error stopping dashboard: $_"
    }
}

# Main logic
if ($Monitor) {
    Write-Host "Starting Ollama Dashboard monitor mode..." -ForegroundColor Cyan
    Write-Host "Checking for Ollama every $CheckInterval seconds..." -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop monitoring" -ForegroundColor Yellow
    Write-Host ""

    $dashboardRunning = $false
    $lastOllamaStatus = $false

    while ($true) {
        $ollamaRunning = Test-OllamaRunning
        $statusChanged = $ollamaRunning -ne $lastOllamaStatus

        if ($ollamaRunning) {
            if (-not $lastOllamaStatus) {
                Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): Ollama detected - starting dashboard..." -ForegroundColor Green
            }
            if ($statusChanged -or -not $dashboardRunning) {
                Stop-Dashboard
                $dashboardProcess = Start-Dashboard
                $dashboardRunning = $null -ne $dashboardProcess
            }
        }
        else {
            if ($lastOllamaStatus) {
                Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'): Ollama stopped - stopping dashboard..." -ForegroundColor Yellow
                Stop-Dashboard
                $dashboardRunning = $false
            }
        }

        $lastOllamaStatus = $ollamaRunning
        Start-Sleep -Seconds $CheckInterval
    }
}
else {
    Write-Host "Checking if Ollama is running..." -ForegroundColor Cyan

    if (Test-OllamaRunning) {
        Write-Host "Ollama is running. Starting dashboard..." -ForegroundColor Green
        $dashboardProcess = Start-Dashboard

        if ($dashboardProcess) {
            Write-Host "Dashboard started successfully!" -ForegroundColor Green
            Write-Host "You can access it at: http://localhost:5000" -ForegroundColor Cyan
        }
        else {
            Write-Error "Failed to start dashboard"
            exit 1
        }
    }
    else {
        Write-Host "Ollama is not running. Please start Ollama first." -ForegroundColor Red
        Write-Host "You can start Ollama with: ollama serve" -ForegroundColor Yellow
        exit 1
    }
}
