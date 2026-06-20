# Ollama Dashboard

## Version 1.2.0

![Ollama Dashboard — system metrics, running/available models with Start, Ask?, Info, Settings and Delete actions, per-model settings with Saved/Default badge](image.png)

A simple web dashboard for **Ollama** — the tool that runs AI models on your computer. See your system usage, start and stop models, change settings, and download new models from one page.

---

## What you can do

- **Start, stop, and manage models** — running, available, and downloadable lists on one screen
- **Watch your computer** — live CPU, RAM, GPU memory, and disk usage
- **Save per-model settings** — temperature, context size, and more (stored in `model_settings.json`)
- **Control Ollama** — start, stop, or restart the Ollama service from the header
- **Connect other apps** — use the built-in **API proxy** URL in the header so VS Code, Copilot, Continue, and similar tools use your saved settings (with parameter sanitization and output caps for IDE clients)
- **MCP tools server** — connect Cursor or VS Code to `http://…/mcp` for dashboard tools (models, stats, proxy status); **Ask?** uses the same tools in agent mode on tool-capable models

The dashboard works in **dark and light** themes and adapts to phone, tablet, and desktop screens.

---

## Quick start

### What you need

1. **Python 3.8+** — [python.org](https://www.python.org/downloads/)
2. **Ollama** — [ollama.com](https://ollama.com) installed and running at `http://localhost:11434`

### Windows

```bash
git clone https://github.com/bazoukajo/ollama-dashboard.git
cd ollama-dashboard
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
start.bat
```

Open **http://localhost:5000** in your browser.

For development with auto-reload, use `start_dev.bat` instead of `start.bat`.

**Manage the running instance (Windows):**

| Script | Purpose |
|--------|---------|
| `start.bat` | Release server (Waitress, production) |
| `start_dev.bat` | Development server (Flask debug + auto-reload) |
| `stop_app.bat` | Stop the dashboard instance on port 5000 |
| `restart_app.bat` | Restart in the same mode (or `restart_app.bat dev` / `release`) |

Scripts detect **release**, **dev**, and **CLI** (`ollama_dashboard_cli.py`) processes for this repo. They stop only dashboard processes — not other apps on port 5000. Shared logic lives in `scripts/dashboard-process.ps1`.

### Linux / macOS

```bash
git clone https://github.com/bazoukajo/ollama-dashboard.git
cd ollama-dashboard
pip install -r requirements.txt
python OllamaDashboard.py
```

Open **http://localhost:5000** in your browser.

### Docker

```bash
docker-compose up -d
```

Then open **http://localhost:5000**.

If Ollama runs on your host machine (not inside Docker), set `OLLAMA_HOST=host.docker.internal` when starting the container — see the [Deployment Guide](docs/DEPLOYMENT.md).

### Run at Windows startup

Copy `StartupFolder\Start Ollama Dashboard.bat` into your Startup folder (**Win+R** → `shell:startup` → Enter). Details in `StartupFolder\README.txt`.

---

## Using the dashboard

1. **Header** — Ollama health, version, backend URL (`http://host:port`), refresh countdown, and theme toggle
2. **System Resources** — live metrics with small history sparklines
3. **Running Models** — models loaded in memory; use **Start** / **Stop** / **Settings** on each card
4. **Available Models** — models on disk; download or delete from here
5. **API proxy** — copy the `http://…/ollama` address to point external apps at the dashboard instead of Ollama directly (your saved settings apply on chat requests)
6. **MCP tools** — copy `http://…/mcp` from **Connect** for Cursor/VS Code MCP; pair with the proxy URL above (models + tools)

Click **Refresh** or wait for the countdown to update model lists. System stats refresh about every second.

---

## Common issues

| Problem | What to try |
|--------|-------------|
| Page won't load | Is the dashboard running? Did you open `http://localhost:5000`? Run `start.bat` or check with `stop_app.bat` then restart |
| Port 5000 already in use | Run `stop_app.bat`, or `restart_app.bat`. If another app owns the port, the stop script will refuse to kill it |
| No models shown | Is Ollama running? Check `http://localhost:11434` or the Ollama URL in the header |
| List looks wrong | Click **Refresh** in the header or reload the page |
| Saved settings ignored by another app | That app may be talking to Ollama directly — use the dashboard **API proxy** URL instead. See [Complete Guide](docs/GUIDE.md) |
| VS Code Copilot: "Response too long" | Point Copilot at `http://127.0.0.1:5000/ollama` (dashboard proxy). It caps output and strips bad parameters automatically |

More help: **[Troubleshooting](docs/TROUBLESHOOTING.md)**

---

## Documentation

| Guide | Contents |
|-------|----------|
| **[Complete Guide](docs/GUIDE.md)** | Proxy setup, MCP tools, Windows start/stop/restart, per-model settings, configuration, development |
| **[Architecture](docs/ARCHITECTURE.md)** | How the app is built internally |
| **[Deployment](docs/DEPLOYMENT.md)** | Docker, Gunicorn, Nginx, production tips |
| **[Security](docs/SECURITY.md)** | CORS, validation, TLS |
| **[Troubleshooting](docs/TROUBLESHOOTING.md)** | Empty model lists, API errors, logging |
| **[Contributing](CONTRIBUTING.md)** | Tests, lint, pull requests |

---

## Install from PyPI or a wheel

```bash
pip install ollama-dashboard
ollama-dashboard
# Opens at http://127.0.0.1:5000
```

Build from source:

```bash
pip install build
python -m build
pip install dist/ollama_dashboard-*-py3-none-any.whl
ollama-dashboard
```

Override listen address with `OLLAMA_DASHBOARD_HOST` and `OLLAMA_DASHBOARD_PORT`.

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Contributing & support

- **Issues:** [GitHub Issues](https://github.com/bazoukajo/ollama-dashboard/issues)
- **Contributing:** fork, add tests, run `python -m pytest -q`, open a PR — see [CONTRIBUTING.md](CONTRIBUTING.md)
- **Community:** [Ollama Discord](https://discord.gg/ollama)

### Donate

If this project helps you, you can support ongoing development:

- [Buy Me a Coffee](https://buymeacoffee.com/bazoukajo)

Thanks for helping this tool keep advancing.
