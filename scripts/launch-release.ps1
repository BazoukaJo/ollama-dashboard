# Start Ollama Dashboard in release mode (Waitress).
# Prefer scripts\start-release.bat on Windows — it avoids WScript / hidden Start-Process
# APIs that Application Control policies often block.
param(
    [switch]$ShowConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BatchLauncher = Join-Path $PSScriptRoot 'start-release.bat'

if (-not (Test-Path $BatchLauncher)) {
    Write-Error "Missing launcher: $BatchLauncher"
    exit 1
}

$arg = if ($ShowConsole) { 'console' } else { '' }
if ($arg) {
    & cmd.exe /c "`"$BatchLauncher`" $arg"
} else {
    & cmd.exe /c "`"$BatchLauncher`""
}
exit $LASTEXITCODE
