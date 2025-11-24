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
        $pythonProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*OllamaDashboard.py*" }
        return $pythonProcesses.Count -gt 0
    }
    catch {
        return $false
    }
}

function Start-Dashboard {
    try {
        $dashboardDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        Push-Location $dashboardDir

        $process = Start-Process -FilePath "python" -ArgumentList "OllamaDashboard.py" -WorkingDirectory $dashboardDir -NoNewWindow -PassThru
        Write-Log "Dashboard started (PID: $($process.Id))"
        return $true
    }
    catch {
        Write-Log "Failed to start dashboard: $_"
        return $false
    }
    finally {
        Pop-Location
    }
}

function Stop-Dashboard {
    try {
        $pythonProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*OllamaDashboard.py*" }

        $stopped = 0
        foreach ($process in $pythonProcesses) {
            Stop-Process -Id $process.Id -Force
            Write-Log "Stopped dashboard process (PID: $($process.Id))"
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
