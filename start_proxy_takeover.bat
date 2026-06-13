@echo off
setlocal enabledelayedexpansion
echo ============================================================
echo  Ollama Settings Proxy - PORT TAKEOVER MODE
echo ============================================================
echo.
echo Takes over Ollama's default port (11434) so EVERY client that
echo assumes Ollama lives at its default address - VS Code
echo extensions, "ollama run", curl, LangChain, etc. - transparently
echo gets your saved per-model settings injected, with ZERO
echo per-client configuration changes.
echo.
echo PREREQUISITE (one-time setup): the real Ollama must already be
echo relocated off port 11434 - set a persistent OLLAMA_HOST env var
echo to "host:port" (e.g. 127.0.0.1:11436) in the environment that
echo launches Ollama, then restart Ollama. See docs\GUIDE.md, section
echo "Per-Model Settings: scope and limitations", for the full guide.
echo.

if not exist node_modules (
    echo [ERROR] node_modules not found. Install dependencies first:
    echo.
    echo     npm install
    echo.
    pause
    exit /b 1
)

if "%OLLAMA_HOST%"=="" (
    echo [WARNING] OLLAMA_HOST is not set in this environment.
    echo This proxy is about to listen on port 11434 and, by default,
    echo forward to localhost:11434 - the SAME port. Unless Ollama has
    echo been relocated via a persistent OLLAMA_HOST, this will conflict
    echo with Ollama itself instead of taking over for it.
    echo.
    set /p "CONTINUE=Continue anyway? [y/N] "
    if /i not "!CONTINUE!"=="y" (
        echo Aborted. Relocate Ollama first ^(see PREREQUISITE above^), then re-run this script.
        exit /b 1
    )
) else (
    echo Forwarding upstream to OLLAMA_HOST=%OLLAMA_HOST%
    echo Make sure that is where the real, relocated Ollama is listening.
)

echo.
echo Starting proxy on port 11434 (Ollama's now-vacated default)...
echo Press Ctrl+C to stop.
echo.

set "PROXY_PORT=11434"
call npm run proxy

endlocal
