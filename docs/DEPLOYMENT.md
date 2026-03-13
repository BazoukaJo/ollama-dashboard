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

# Run (production, uses Waitress)
start_app.bat

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

| Script | Purpose |
|--------|---------|
| `start_app.bat` | Start the dashboard with Waitress (production WSGI server) |
| `stop_app.bat` | Stop the dashboard (kills process on port 5000) |
| `restart_app.bat` | Stop then start the dashboard in a new window |

The PowerShell monitor script (`scripts/ollama-dashboard-monitor.ps1`) can auto-start the dashboard when Ollama is detected and stop it when Ollama shuts down.

---

## Environment Setup

### Configuration via Environment Variables

Create a `.env` file (not committed to git):

```bash
# Ollama connection
OLLAMA_HOST=localhost
OLLAMA_PORT=11434

# Persistence
HISTORY_FILE=history.json
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
| `start_app.bat` window closes immediately | Run from an existing terminal to see errors; ensure `.venv` exists with `waitress` installed |
| Settings changes not saving | Check file permissions; ensure disk space available |
| Port 5000 already in use | Run `stop_app.bat` first, or check `netstat -aon \| findstr :5000` |

---

## Backup & Restore

### Backup
```bash
# Backup settings and history
tar czf ollama-dashboard-backup-$(date +%Y%m%d).tar.gz \
  model_settings.json \
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
