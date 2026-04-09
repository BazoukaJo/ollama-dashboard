# Release Notes

## Version 1.0005 (2026)

- **Client robustness** — Shared `readApiJson()` (`js/modules/utils.js`): every dashboard `fetch` path reads the body once, tolerates non-JSON errors, and avoids `response.json()` throws. Applied across `main.js`, `serviceControl.js`, `settings.js`, and `modelCardActions.js`.
- **System stats** — Defensive numeric handling when `/api/system/stats` returns an unexpected shape (no thrown `toFixed` on `undefined`).
- **Health / service actions** — Restart, install, and update flows use the same safe parsing; health polling treats missing `uptime_seconds` as zero.

## Version 1.0004 (2026)

- **Quality bar** — `ruff check` on `app/`, `tests/`, and `scripts/` in CI (`lint` job); config in `pyproject.toml` (Python 3.8–compatible rule set).
- **Project metadata** — `pyproject.toml` documents the package name, version, and `pytest` markers; `requirements-dev.txt` for optional local lint (`pip install -r requirements-dev.txt`).
- **Contributing** — [CONTRIBUTING.md](CONTRIBUTING.md) describes how to run tests and lint before opening a PR.
- **Code hygiene** — Ruff-driven cleanup (unused imports, explicit re-exports in `app.routes`, safer `except` in helpers, Playwright availability via `importlib`).

## Version 1.0003 (2026)

- **Header** — Sticky top bar with Ollama logo (left-aligned), health badge, and service controls; dashboard / Ollama versions and API host moved to a compact strip below that scrolls with the page. Narrow viewports use a fixed row layout (brand + theme, then full-width health, then controls) to avoid awkward flex wrapping.
- **Scrolling** — Removed top padding above the sticky header and reserved stable scrollbar gutter so the bar does not “creep” a few pixels before locking.
- **Tooltips** — Broader, practical `data-dashboard-tooltip` copy on cards, filters, and controls; hover tooltips wait briefly before opening to reduce accidental flashes.
- **Cards** — Stronger contrast for spec tiles (labels, values, icons) in light and dark themes; model action buttons use a responsive grid (primary actions first, full-width Start on available cards) instead of a rigid three-per-row strip.
- **Settings status** — Running and available cards always show a compact **Saved** or **Default** badge on the Settings control (per-model `model_settings.json` state).
- **Downloadable cards** — Same action layout class for the single Download control.
- **Docs** — README screenshot updated (`docs/images/dashboard.png`).
- **Reliability** — `/api/*` errors return JSON (no stray HTML parse errors in the UI); model settings use `?model=` so names with `/` or `:` route correctly; running-model list avoids trusting a cached empty `/api/ps` result and retries briefly; capability filters no longer hide loaded models.
- **Windows** — Install/update flows treat a healthy Ollama API as success when winget/choco exit codes are misleading; broader winget “already installed / reboot” handling.
- **Validation** — Model IDs may include `/` (library paths) and `+` (quant suffixes); admin “model defaults” page uses the same settings URLs as the main dashboard.
- **Polling** — System stats refresh on the same interval as the model-list countdown (and pause when the tab is hidden).

## Version 1.0002 (2026)

- UI: streamlined header (versions row + Ollama mark), more downloadable models before “View More”, compact toggle optional via [docs/UI.md](docs/UI.md).
- Models: card “More” menu (copy CLI/curl, library link, quick chat, copy settings), settings copy API, recent error strip, quantization row when available.
- Polling: model list refresh on the countdown; Ollama install detection vs API version; `OLLAMA_HOST` with embedded port normalized for display and URLs.
- Docs: [docs/UI.md](docs/UI.md) for UI toggles and layout constants.

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
- [Buy Me a Coffee ☕](https://buymeacoffee.com/bazoukajo)
