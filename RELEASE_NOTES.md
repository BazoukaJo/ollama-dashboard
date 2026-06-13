# Release Notes

## Version 1.2.0 (2026)

- **Benchmark-backed model defaults** — `model_recommendation_profiles.json` applies family-specific settings (Qwen3, DeepSeek-R1, coders, Llama 3, vision, etc.) sourced from official model cards. Context sizing respects model window and local VRAM/RAM caps. **Apply Recommended** and `/api/models/settings/recommended` always recompute fresh values.
- **Apply all recommended** — `POST /api/models/settings/apply_all_recommended` skips models with `source: user` so custom saves (e.g. a higher `num_ctx`) are not overwritten. Admin page shows applied/skipped counts.
- **Copilot proxy fix** — `/ollama/v1/chat/completions` passthroughs to Ollama's native v1 endpoint with saved settings merged into `options` (including `num_ctx`). Preserves Copilot-compatible SSE for reasoning models and Agent-mode tool calls. `/v1/completions` still bridges to `/api/generate` via `v1_native_bridge.py`. Streaming upstream errors return proper SSE error chunks.
- **Profile coverage** — Added patterns for `qwen3.6`, `gemma4`, `nemotron`, `lfm2.5`, and related current Ollama library names.
- **Docs** — README, ARCHITECTURE, and TROUBLESHOOTING updated for Copilot v1 passthrough; troubleshooting entry for "Sorry, no response was returned".

## Version 1.1.0 (2026)

- **Python package** — `pyproject.toml` is a full setuptools project: runtime dependencies, `package-data` for `app` templates/static/JSON, and console script **`ollama-dashboard`** (`ollama_dashboard_cli.py`). Version is **PEP 440**–compliant (`1.1.0`; legacy tags like `1.0005` normalize to `1.5` on PyPI). Build with `python -m build`; install with `pip install dist/*.whl` or publish via `twine` (see README).
- **Settings-injecting proxy fixes** — both the dashboard's built-in `/ollama/api/...` proxy (`intercept_ollama_parameters` in `app/__init__.py`) and the standalone `server_with_proxy.js` had bugs that could silently stop saved per-model settings from ever reaching Ollama for external clients (VS Code, `ollama run`, etc.): merging the *whole* stored `{settings, source, last_updated}` entry instead of just its inner `settings` dict, and — whenever `OLLAMA_HOST` carried an embedded port (`host:port`) — double-porting the upstream URL into `http://127.0.0.1:11436:11434`. Both fixed in both proxies, which now share the same `_get_ollama_host_port()` / `resolveOllamaHostPort()` resolution as the rest of the app. New regression suite: `tests/test_ollama_proxy_interceptor.py`.
- **Port-takeover deployment mode** — `server_with_proxy.js` can now stand in for Ollama at Ollama's *own* default address (`:11434`): relocate the real Ollama via `OLLAMA_HOST=host:port` and run the proxy on the vacated port, and every client that assumes Ollama lives at its default address (VS Code, `ollama run`, curl, LangChain, ...) gets saved settings transparently — zero per-client reconfiguration. New `start_proxy_takeover.bat` launcher automates the takeover with pre-flight checks. See [docs/GUIDE.md](docs/GUIDE.md#per-model-settings-scope-and-limitations).
- **GitHub Copilot / OpenAI-compatible proxy** — built-in `/ollama/v1/chat/completions` and `/ollama/v1/models` routes (`app/routes/proxy.py`); saved settings merged on inference. Fixes Waitress 500 when passthrough forwarded hop-by-hop headers from Ollama. Docs updated for Copilot endpoint `http://127.0.0.1:5000/ollama`.

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

- UI: streamlined header (versions row + Ollama mark), more downloadable models before “View More”.
- Models: card “More” menu (copy CLI/curl, library link, quick chat, copy settings), settings copy API, recent error strip, quantization row when available.
- Polling: model list refresh on the countdown; Ollama install detection vs API version; `OLLAMA_HOST` with embedded port normalized for display and URLs.
- Docs: [docs/UI.md](docs/UI.md) for layout constants.

## Version 1.0001 (2025)

First stable release of Ollama Dashboard: a web UI to monitor, control, and manage Ollama models and the Ollama service.

### Highlights

- **Model management** — Start, stop, restart, delete, and download models from the dashboard. Running and available models are listed with one-time load and manual refresh (no background polling of the model list).
- **System monitoring** — Real-time CPU, RAM, VRAM, and GPU utilization with 1-second updates and simple timeline views.
- **Health & service control** — Health status every 15 seconds; start, stop, and restart the Ollama service (including on Windows).
- **Capabilities** — Vision, tools, and reasoning indicators on model cards, using Ollama `/api/show` when available and per-model caching to limit repeated calls.
- **Per-model settings** — Temperature, top-k, and related parameters with JSON-backed persistence, applied to requests made through the dashboard (chat, warm-load, restart) *and*, for external clients (VS Code, `ollama run`, etc.), via the dashboard's built-in settings-injecting proxy at `/ollama/api/...` (point a client's base URL at `http://<dashboard-host>:<port>/ollama`), **Bake into Model** (derived `<model>-dashboard` with `PARAMETER` directives), or the standalone `server_with_proxy.js` — see [Complete Guide: Per-Model Settings](docs/GUIDE.md#per-model-settings-scope-and-limitations).
- **Model discovery** — Browse and download from a curated list; “Find Model” search with input focused when the modal opens.
- **UI** — Dark theme, capability filters for available and downloadable models, and reduced vertical spacing in the uncollapsed layout.

### Requirements

- Python 3.8+
- Ollama (default: localhost:11434)

### Install & run

- **Windows:** `python -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt`, then `start.bat`. Open <http://localhost:5000>.
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
