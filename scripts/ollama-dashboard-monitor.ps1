# Ollama Dashboard Service Monitor
# This script runs as a background service to monitor Ollama and manage the dashboard

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Status,
    [int]$CheckInterval = 5
)

$ServiceName = "OllamaDashboardMonitor"
$ScriptPath = $PSScriptRoot + "\ollama-dashboard-monitor.ps1"
$LogFile = "$env:TEMP\ollama-dashboard-monitor.log"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $LogFile -Append
    Write-Host "[$timestamp] $Message"
}

function Test-OllamaRunning {
    try {
        $ollamaProcess = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
        return $null -ne $ollamaProcess
    }
    catch {
        return $false
    }
}

function Test-DashboardRunning {
    try {
        $listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
        return $null -ne $listener
    }
    catch {
        return $false
    }
}

function Start-Dashboard {
    try {
        $dashboardDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        $venvPython = Join-Path $dashboardDir ".venv\Scripts\python.exe"
        $waitress = Join-Path $dashboardDir ".venv\Scripts\waitress-serve.exe"

        if (-not (Test-Path $waitress)) {
            Write-Log "waitress-serve not found at $waitress"
            return $false
        }

        $process = Start-Process -FilePath $waitress `
            -ArgumentList "--call", "--host=0.0.0.0", "--port=5000", "--threads=8", "app:create_app" `
            -WorkingDirectory $dashboardDir -NoNewWindow -PassThru
        Write-Log "Dashboard started (PID: $($process.Id))"
        return $true
    }
    catch {
        Write-Log "Failed to start dashboard: $_"
        return $false
    }
}

function Stop-Dashboard {
    try {
        $stopped = 0
        $listeners = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $listeners) {
            $pid = $conn.OwningProcess
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Log "Stopped dashboard process (PID: $pid)"
            $stopped++
        }

        if ($stopped -eq 0) {
            Write-Log "No dashboard processes found to stop"
        }

        return $true
    }
    catch {
        Write-Log "Error stopping dashboard: $_"
        return $false
    }
}

function Install-Service {
    Write-Host "Installing Ollama Dashboard Monitor service..." -ForegroundColor Cyan

    # Check if running as administrator
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Error "Please run as Administrator to install the service"
        exit 1
    }

    try {
        # Create a scheduled task that runs on system startup
        $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`" -Monitor"
        $trigger = New-ScheduledTaskTrigger -AtStartup
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType InteractiveToken

        Register-ScheduledTask -TaskName $ServiceName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Monitors Ollama and manages the Ollama Dashboard"

        Write-Host "Service installed successfully!" -ForegroundColor Green
        Write-Host "The monitor will start automatically when you log in." -ForegroundColor Cyan
    }
    catch {
        Write-Error "Failed to install service: $_"
    }
}

function Uninstall-Service {
    Write-Host "Uninstalling Ollama Dashboard Monitor service..." -ForegroundColor Cyan

    try {
        # Stop any running instances first
        Stop-Dashboard

        # Remove the scheduled task
        Unregister-ScheduledTask -TaskName $ServiceName -Confirm:$false

        Write-Host "Service uninstalled successfully!" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to uninstall service: $_"
    }
}

function Start-ServiceMonitor {
    Write-Host "Starting Ollama Dashboard Monitor..." -ForegroundColor Green

    try {
        Start-ScheduledTask -TaskName $ServiceName
        Write-Host "Monitor started successfully!" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to start monitor: $_"
    }
}

function Stop-ServiceMonitor {
    Write-Host "Stopping Ollama Dashboard Monitor..." -ForegroundColor Yellow

    try {
        Stop-ScheduledTask -TaskName $ServiceName
        Stop-Dashboard  # Also stop any running dashboard
        Write-Host "Monitor stopped successfully!" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to stop monitor: $_"
    }
}

function Get-ServiceStatus {
    Write-Host "Ollama Dashboard Monitor Status:" -ForegroundColor Cyan
    Write-Host "------------------------------" -ForegroundColor Cyan

    try {
        $task = Get-ScheduledTask -TaskName $ServiceName -ErrorAction SilentlyContinue
        if ($task) {
            Write-Host "Service: Installed" -ForegroundColor Green
            Write-Host "Status: $($task.State)" -ForegroundColor $(if ($task.State -eq 'Running') { 'Green' } else { 'Yellow' })
        }
        else {
            Write-Host "Service: Not Installed" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "Service: Error checking status" -ForegroundColor Red
    }

    $ollamaRunning = Test-OllamaRunning
    $dashboardRunning = Test-DashboardRunning

    Write-Host ""
    Write-Host "Current Status:" -ForegroundColor Cyan
    Write-Host "Ollama: $(if ($ollamaRunning) { 'Running' } else { 'Stopped' })" -ForegroundColor $(if ($ollamaRunning) { 'Green' } else { 'Red' })
    Write-Host "Dashboard: $(if ($dashboardRunning) { 'Running' } else { 'Stopped' })" -ForegroundColor $(if ($dashboardRunning) { 'Green' } else { 'Red' })
}

function Start-Monitor {
    Write-Log "Starting Ollama Dashboard monitor mode..."
    Write-Log "Checking for Ollama every $CheckInterval seconds..."

    $dashboardRunning = $false
    $lastOllamaStatus = $false

    while ($true) {
        $ollamaRunning = Test-OllamaRunning
        $statusChanged = $ollamaRunning -ne $lastOllamaStatus

        if ($ollamaRunning) {
            if (-not $lastOllamaStatus) {
                Write-Log "Ollama detected - starting dashboard..."
            }

            if ($statusChanged -or -not $dashboardRunning) {
                Stop-Dashboard
                $dashboardRunning = Start-Dashboard
            }
        }
        else {
            if ($lastOllamaStatus) {
                Write-Log "Ollama stopped - stopping dashboard..."
                $dashboardRunning = -not (Stop-Dashboard)
            }
        }

        $lastOllamaStatus = $ollamaRunning
        Start-Sleep -Seconds $CheckInterval
    }
}

# Main logic
if ($Install) {
    Install-Service
}
elseif ($Uninstall) {
    Uninstall-Service
}
elseif ($Start) {
    Start-ServiceMonitor
}
elseif ($Stop) {
    Stop-ServiceMonitor
}
elseif ($Status) {
    Get-ServiceStatus
}
else {
    # Default: run monitor
    Start-Monitor
}
