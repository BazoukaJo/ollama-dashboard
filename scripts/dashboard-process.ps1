# Shared dashboard process detection and lifecycle for Windows batch launchers.
param(
    [ValidateSet('status', 'stop', 'wait-clear', 'ensure-port', 'resolve-mode')]
    [string]$Action = 'status',
    [ValidateSet('release', 'dev', 'any')]
    [string]$Mode = 'any',
    [int]$Port = 5000,
    [int]$WaitSeconds = 12,
    [string]$RepoRoot = '',
    [switch]$CloseLaunchers
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}
$RepoRootNorm = $RepoRoot.TrimEnd('\')

function Get-ProcessCommandLine {
    param([int]$ProcessId)
    try {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        return [string]$p.CommandLine
    } catch {
        return ''
    }
}

function Get-ProcessMode {
    param([string]$CommandLine)
    if (-not $CommandLine) { return 'unknown' }
    if ($CommandLine -match 'waitress-serve|-m waitress') { return 'release' }
    if ($CommandLine -match 'flask run') { return 'dev' }
    if ($CommandLine -match 'ollama_dashboard_cli|OllamaDashboard\.py') { return 'cli' }
    if ($CommandLine -match 'wsgi:app') { return 'release' }
    if ($CommandLine -match 'create_app') { return 'release' }
    return 'unknown'
}

function Test-DashboardCommandLine {
    param([string]$CommandLine)
    if (-not $CommandLine) { return $false }

    $inRepo = $CommandLine -like "*$RepoRootNorm*"
    $mentionsPort = $CommandLine -match ":$Port\b|--port=$Port\b|--port $Port\b"
    $signature = $CommandLine -match 'waitress-serve|-m waitress|flask run|ollama_dashboard_cli|OllamaDashboard\.py|wsgi:app|create_app'

    if (-not $signature) { return $false }
    return ($inRepo -or $mentionsPort)
}

function Get-DashboardProcessRecords {
    $records = @()
    $seen = @{}

    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    foreach ($proc in $all) {
        $cmd = [string]$proc.CommandLine
        if (-not (Test-DashboardCommandLine $cmd)) { continue }
        $procId = [int]$proc.ProcessId
        if ($seen.ContainsKey($procId)) { continue }
        $seen[$procId] = $true
        $records += [pscustomobject]@{
            ProcessId   = $procId
            ParentId    = [int]$proc.ParentProcessId
            Mode        = Get-ProcessMode $cmd
            CommandLine = $cmd
            Role        = 'launcher'
        }
    }

    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $listeners) {
            $procId = [int]$conn.OwningProcess
            if ($seen.ContainsKey($procId)) {
                ($records | Where-Object ProcessId -eq $procId).Role = 'listener'
                continue
            }
            $cmd = Get-ProcessCommandLine $procId
            if (Test-DashboardCommandLine $cmd) {
                $seen[$procId] = $true
                $records += [pscustomobject]@{
                    ProcessId   = $procId
                    ParentId    = 0
                    Mode        = Get-ProcessMode $cmd
                    CommandLine = $cmd
                    Role        = 'listener'
                }
            } else {
                $seen[$procId] = $true
                $records += [pscustomobject]@{
                    ProcessId   = $procId
                    ParentId    = 0
                    Mode        = 'foreign'
                    CommandLine = $cmd
                    Role        = 'foreign-listener'
                }
            }
        }
    } catch {
        # Older Windows without Get-NetTCPConnection
    }

    return $records
}

function Get-RunModeFile {
    $path = Join-Path $RepoRootNorm 'data\dashboard.run-mode'
    if (-not (Test-Path $path)) { return '' }
    return (Get-Content $path -Raw).Trim().ToLowerInvariant()
}

function Get-DashboardStatus {
    $records = @(Get-DashboardProcessRecords)
    $listeners = @($records | Where-Object Role -eq 'listener')
    $foreign = @($records | Where-Object Role -eq 'foreign-listener')
    $dashboard = @($records | Where-Object Role -ne 'foreign-listener')

    $runningMode = ''
    if ($listeners.Count -gt 0 -and $foreign.Count -eq 0) {
        $runningMode = ($listeners | Select-Object -First 1 -ExpandProperty Mode)
    } elseif ($dashboard.Count -gt 0) {
        $runningMode = ($dashboard | Select-Object -First 1 -ExpandProperty Mode)
    }

    $savedMode = Get-RunModeFile
    $portBusy = ($listeners.Count + $foreign.Count) -gt 0

    return [pscustomobject]@{
        Running          = $dashboard.Count -gt 0 -or $foreign.Count -gt 0
        DashboardRunning = $dashboard.Count -gt 0
        PortBusy         = $portBusy
        ForeignOnPort    = $foreign.Count -gt 0
        Mode             = $runningMode
        SavedMode        = $savedMode
        Processes        = $records
        ListenerPids     = @($listeners | ForEach-Object { $_.ProcessId })
        ForeignPids      = @($foreign | ForEach-Object { $_.ProcessId })
        DashboardPids    = @($dashboard | ForEach-Object { $_.ProcessId })
    }
}

function Stop-DashboardProcesses {
    $status = Get-DashboardStatus
    if ($status.ForeignOnPort) {
        Write-Host "Port $Port is used by a non-dashboard process (PID $($status.ForeignPids -join ', '))."
        Write-Host "Refusing to kill foreign process. Stop it manually or change the dashboard port."
        return 2
    }
    if (-not $status.DashboardRunning -and -not $status.PortBusy) {
        Write-Host "No dashboard instance is running on port $Port."
        return 1
    }

    $targets = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($rec in $status.Processes) {
        if ($rec.Role -eq 'foreign-listener') { continue }
        [void]$targets.Add($rec.ProcessId)
    }

    $stopped = 0
    foreach ($targetId in $targets) {
        $killed = $false
        try {
            & taskkill /PID $targetId /T /F 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Stopped process tree PID $targetId"
                $killed = $true
            }
        } catch { }
        if (-not $killed) {
            try {
                Stop-Process -Id $targetId -Force -ErrorAction Stop
                Write-Host "Stopped PID $targetId"
                $killed = $true
            } catch { }
        }
        if ($killed) { $stopped++ }
    }

    if ($stopped -eq 0) { return 1 }
    return 0
}

function Get-DashboardLauncherProcessIds {
    $ids = New-Object 'System.Collections.Generic.HashSet[int]'
    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    foreach ($proc in $all) {
        if ($proc.Name -ne 'cmd.exe') { continue }
        $cmd = [string]$proc.CommandLine
        if (-not $cmd) { continue }
        if ($cmd -notlike "*$RepoRootNorm*") { continue }
        if ($cmd -match 'start(_dev)?\.bat') {
            [void]$ids.Add([int]$proc.ProcessId)
        }
    }
    return @($ids)
}

function Stop-DashboardLaunchers {
    param([int[]]$ProcessIds = @())

    if ($ProcessIds.Count -eq 0) {
        $ProcessIds = @(Get-DashboardLauncherProcessIds)
    }

    $stopped = 0
    foreach ($launcherId in $ProcessIds) {
        try {
            & taskkill /PID $launcherId /T /F 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Closed launcher window PID $launcherId"
                $stopped++
            }
        } catch { }
    }
    return $stopped
}

function Wait-PortClear {
    for ($i = 0; $i -lt $WaitSeconds; $i++) {
        $busy = $false
        try {
            $busy = $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        } catch { $busy = $false }
        if (-not $busy) { return 0 }
        Start-Sleep -Seconds 1
    }
    return 1
}

function Initialize-PortForMode {
    param([string]$TargetMode)
    $status = Get-DashboardStatus
    if ($status.ForeignOnPort) { return 2 }
    if (-not $status.DashboardRunning -and -not $status.PortBusy) { return 0 }

    $current = $status.Mode
    if ($current -eq $TargetMode -or ($TargetMode -eq 'release' -and $current -in @('release', 'cli'))) {
        Write-Host "Dashboard already running ($current) on port $Port (PID $($status.ListenerPids -join ', '))."
        return 3
    }

    Write-Host "Port $Port is in use by dashboard mode '$current'; stopping before starting '$TargetMode'..."
    $code = Stop-DashboardProcesses
    if ($code -ne 0) { return $code }
    return (Wait-PortClear)
}

function Resolve-RestartMode {
    $status = Get-DashboardStatus
    if ($status.Mode -eq 'dev') { return 'dev' }
    if ($status.Mode -in @('release', 'cli')) { return 'release' }
    $saved = Get-RunModeFile
    if ($saved -eq 'dev') { return 'dev' }
    return 'release'
}

function Write-StatusReport {
    $status = Get-DashboardStatus
    if ($status.ForeignOnPort) {
        Write-Host "Port $Port blocked by non-dashboard PID(s): $($status.ForeignPids -join ', ')"
        exit 4
    }
    if ($status.DashboardRunning) {
        $mode = if ($status.Mode) { $status.Mode } else { 'unknown' }
        $saved = if ($status.SavedMode) { $status.SavedMode } else { 'unknown' }
        Write-Host "Dashboard running: mode=$mode saved=$saved port=$Port pid=$($status.ListenerPids -join ', ')"
        exit 0
    }
    Write-Host "Dashboard not running (port $Port free)."
    exit 1
}

switch ($Action) {
    'status' { Write-StatusReport }
    'resolve-mode' {
        Write-Output (Resolve-RestartMode)
        exit 0
    }
    'stop' {
        $launcherIds = @()
        if ($CloseLaunchers) {
            $launcherIds = @(Get-DashboardLauncherProcessIds)
        }
        $code = Stop-DashboardProcesses
        if ($CloseLaunchers) {
            Stop-DashboardLaunchers -ProcessIds $launcherIds | Out-Null
            Stop-DashboardLaunchers | Out-Null
        }
        if ($code -eq 0) { Wait-PortClear | Out-Null }
        exit $code
    }
    'wait-clear' { exit (Wait-PortClear) }
    'ensure-port' { exit (Initialize-PortForMode -TargetMode $Mode) }
}
