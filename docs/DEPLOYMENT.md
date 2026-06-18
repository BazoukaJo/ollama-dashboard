# Ollama Dashboard Deployment Guide

## Quick Start

### Prerequisites
- Python 3.8+
- Ollama running on localhost:11434

### Windows

```bash
# Clone or download the repository
cd ollama-dashboard

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run (release — Waitress, no debug)
start.bat

# Open in browser
# http://localhost:5000
```

### Linux / macOS (Development)

```bash
cd ollama-dashboard
pip install -r requirements.txt
python OllamaDashboard.py
# http://localhost:5000
```

---

## Windows Management Scripts

All scripts use `scripts/dashboard-process.ps1` to detect and stop the correct dashboard
instance (release Waitress, dev Flask reloader, or `ollama_dashboard_cli.py`). They only stop
dashboard processes for this repo — not unrelated apps on port 5000.

| Script | Purpose |
|--------|---------|
| `start.bat` | Start with Waitress (release, no debug). Skips if release/cli already running; stops dev first if needed |
| `start_dev.bat` | Start with Flask dev server and debug reloader. Skips if dev already running; stops release/cli first if needed |
| `stop_app.bat` | Stop the dashboard; shows status; waits for port 5000 to clear |
| `restart_app.bat` | Stop then restart in the **running** mode (falls back to `data\dashboard.run-mode`). Override: `restart_app.bat dev` or `release` |

**Check what's running:**

```powershell
powershell -File scripts\dashboard-process.ps1 -Action status
```

The PowerShell monitor script (`scripts/ollama-dashboard-monitor.ps1`) can auto-start the dashboard when Ollama is detected and stop it when Ollama shuts down.

> `start_proxy_takeover.bat` is a related but separate script: it runs the *optional*
> settings-injecting companion proxy (`server_with_proxy.js`) in "port takeover" mode — not
> the dashboard itself, and not required to use the dashboard. See the README's
> [Per-Model Settings: scope and limitations](GUIDE.md#per-model-settings-scope-and-limitations)
> for what it does and when you'd want it.

---

## Environment Setup

### Configuration via Environment Variables

Create a `.env` file (not committed to git):

```bash
# Ollama connection
OLLAMA_HOST=localhost
OLLAMA_PORT=11434

# Persistence
HISTORY_FILE=history.json          # model-list snapshots (not chat sessions)
MODEL_SETTINGS_FILE=model_settings.json
MAX_HISTORY=50

# Logging
LOG_LEVEL=INFO
```

### Configuration Priority
1. Environment variables (highest priority)
2. `.env` file
3. Hardcoded defaults (lowest priority)

---

## Docker Deployment

### Single Container

The Docker image uses Gunicorn (Linux) with `wsgi.py` as the entry point.

**Build & Run:**
```bash
docker build -t ollama-dashboard:latest .

docker run -p 5000:5000 \
  -e OLLAMA_HOST=host.docker.internal \
  ollama-dashboard:latest
```

### Docker Compose (with Ollama)

```bash
docker-compose up -d
# Access at http://localhost:5000
```

The included `docker-compose.yml` starts both Ollama and the Dashboard.

---

## Gunicorn + Nginx (Linux Production)

For Linux production deployments, use Gunicorn with the included `wsgi.py`:

```bash
pip install gunicorn

gunicorn \
  --config app/config/gunicorn.py \
  --env OLLAMA_HOST=localhost \
  wsgi:app
```

### Nginx Reverse Proxy

```nginx
upstream ollama_dashboard {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name dashboard.example.com;

    location / {
        proxy_pass http://ollama_dashboard;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /static/ {
        proxy_pass http://ollama_dashboard;
        proxy_cache_valid 200 1d;
        expires 1d;
    }

    location /health {
        proxy_pass http://ollama_dashboard;
        proxy_read_timeout 5s;
    }
}
```

---

## Troubleshooting Deployment

| Issue | Solution |
|-------|----------|
| Dashboard can't connect to Ollama | Check `OLLAMA_HOST` env var; ensure Ollama API is accessible |
| `start.bat` window closes immediately | Run from an existing terminal to see errors; ensure `.venv` exists with `waitress` installed |
| Settings changes not saving | Check file permissions; ensure disk space available |
| Port 5000 already in use | Run `stop_app.bat`. If stop refuses, another app owns the port — see [Troubleshooting](TROUBLESHOOTING.md#dashboard-wont-start-or-stop-windows-port-5000) |
| Started dev but wanted release (or vice versa) | `stop_app.bat` then `start.bat` or `start_dev.bat`; or `restart_app.bat release` / `dev` |

---

## Backup & Restore

### Backup
```bash
# Backup settings and history (paths relative to repo root / working directory)
tar czf ollama-dashboard-backup-$(date +%Y%m%d).tar.gz \
  model_settings.json \
  history.json \
  chat_history.json \
  system_stats_history.json
```

### Restore
```bash
tar xzf ollama-dashboard-backup-*.tar.gz
# Restart the app
```

---

## Cleanup

### Stop Deployment
```bash
# Windows
stop_app.bat

# Docker Compose
docker-compose down

# Linux
pkill -f waitress-serve
# or
pkill -f gunicorn
```
