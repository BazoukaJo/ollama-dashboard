# Release Notes

## Version 1.0001 (2025)

First stable release of Ollama Dashboard: a web UI to monitor, control, and manage Ollama models and the Ollama service.

### Highlights

- **Model management** — Start, stop, restart, delete, and download models from the dashboard. Running and available models are listed with one-time load and manual refresh (no background polling of the model list).
- **System monitoring** — Real-time CPU, RAM, VRAM, and GPU utilization with 1-second updates and simple timeline views.
- **Health & service control** — Health status every 15 seconds; start, stop, and restart the Ollama service (including on Windows).
- **Capabilities** — Vision, tools, and reasoning indicators on model cards, using Ollama `/api/show` when available and per-model caching to limit repeated calls.
- **Per-model settings** — Temperature, top-k, and related parameters with JSON-backed persistence.
- **Model discovery** — Browse and download from a curated list; “Find Model” search with input focused when the modal opens.
- **UI** — Dark theme, compact mode toggle, capability filters for available and downloadable models, and reduced vertical spacing in the uncollapsed layout.

### Requirements

- Python 3.8+
- Ollama (default: localhost:11434)

### Install & run

- **Windows:** `python -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt`, then `start_app.bat`. Open <http://localhost:5000>.
- **Linux/macOS:** Same venv and pip steps, then `python OllamaDashboard.py`.
- **Docker:** `docker build -t ollama-dashboard .` and run with port 5000 and `OLLAMA_HOST` as needed (e.g. `host.docker.internal` on Docker Desktop).

### Windows startup

To start the dashboard with Windows, copy `StartupFolder\Start Ollama Dashboard.bat` into the Startup folder (open with **Win+R** → `shell:startup`).

### Documentation

- [README](README.md) — Quick start, configuration, troubleshooting.
- [Architecture](docs/ARCHITECTURE.md) — Services, data flow, caching.
- [Deployment](docs/DEPLOYMENT.md) — Windows, Docker, Gunicorn, Nginx.
- [Security](docs/SECURITY.md) — Validation, CORS, TLS, secrets.

### Feedback

- [GitHub Issues](https://github.com/bazoukajo/ollama-dashboard/issues)
