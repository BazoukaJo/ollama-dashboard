# Start Ollama Dashboard in release mode (Waitress) without a visible console window.
param(
    [switch]$ShowConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$DataDir = Join-Path $RepoRoot 'data'
$LogFile = Join-Path $DataDir 'dashboard-release.log'
$ErrFile = Join-Path $DataDir 'dashboard-release-error.log'
$LaunchLog = Join-Path $DataDir 'dashboard-release-launch.log'
$ProcessScript = Join-Path $PSScriptRoot 'dashboard-process.ps1'

function Write-LaunchMessage {
    param([string]$Message)
    if ($ShowConsole) {
        Write-Host $Message
        return
    }
    if (-not (Test-Path $DataDir)) {
        New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    }
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $LaunchLog -Value $line -Encoding UTF8
}

function Show-LaunchError {
    param([string]$Message)
    Write-LaunchMessage $Message
    if (-not $ShowConsole) {
        try {
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show(
                $Message,
                'Ollama Dashboard',
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Error
            ) | Out-Null
        } catch {
            # Headless / non-interactive session — log only.
        }
    }
}

if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}

$waitress = Join-Path $RepoRoot '.venv\Scripts\waitress-serve.exe'
if (-not (Test-Path $waitress)) {
    Show-LaunchError 'Release start failed: .venv\Scripts\waitress-serve.exe not found.'
    exit 1
}

& powershell -NoProfile -ExecutionPolicy Bypass -File $ProcessScript -Action ensure-port -Mode release -RepoRoot $RepoRoot | Out-Null
$ensure = $LASTEXITCODE
switch ($ensure) {
    0 { break }
    3 {
        Write-LaunchMessage 'Release dashboard already running on port 5000.'
        exit 3
    }
    2 {
        Show-LaunchError 'Release start failed: port 5000 is used by another application.'
        exit 2
    }
    default {
        Show-LaunchError "Release start failed: could not prepare port 5000 (exit $ensure)."
        exit $ensure
    }
}

'release' | Set-Content -Path (Join-Path $DataDir 'dashboard.run-mode') -NoNewline -Encoding ASCII

$startInfo = @{
    FilePath               = $waitress
    ArgumentList           = @('--host=127.0.0.1', '--port=5000', '--threads=8', 'wsgi:app')
    WorkingDirectory       = $RepoRoot
    WindowStyle            = 'Hidden'
    RedirectStandardOutput = $LogFile
    RedirectStandardError  = $ErrFile
    PassThru               = $true
}

$env:OLLAMA_DASHBOARD_CONFIG = 'production'

try {
    $proc = Start-Process @startInfo
    Write-LaunchMessage "Release dashboard started (PID $($proc.Id)). Server log: data\dashboard-release-error.log Launch log: data\dashboard-release-launch.log"
    exit 0
} catch {
    Show-LaunchError "Release start failed: $_"
    exit 1
}
