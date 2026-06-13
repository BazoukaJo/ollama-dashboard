# Ollama Dashboard — Complete Guide

Detailed setup, configuration, proxy integration, and development reference. For a quick start, see the [README](../README.md).

---

## Architecture

```text
┌──────────────────────────────────────────┐
│         Ollama Dashboard                  │
├──────────────────────────────────────────┤
│ Flask Web Framework (HTTP routing)        │
│ + CORS, Security Headers                │
├──────────────────────────────────────────┤
│ Route Layer (API endpoints)               │
│ + Input validation, Serialization        │
├──────────────────────────────────────────┤
│ OllamaService (Main Orchestrator)        │
│ ├─ OllamaServiceCore (caching, bg)      │
│ ├─ OllamaServiceModels (operations)     │
│ ├─ OllamaServiceControl (service mgmt)  │
│ └─ OllamaServiceUtilities (settings)    │
├──────────────────────────────────────────┤
│ HTTP Client (requests.Session)            │
│ + Connection pooling, Keep-alive         │
├──────────────────────────────────────────┤
│ Ollama API (http://localhost:11434)       │
│ /api/ps, /api/tags, /api/generate, etc.  │
└──────────────────────────────────────────┘
```

See also the [Architecture Guide](ARCHITECTURE.md) for service composition, caching, and concurrency.

---

## Per-Model Settings: scope and limitations

Per-model settings (temperature, top-k, top-p, context size, penalties, stop sequences, etc.)
are saved to `model_settings.json` (see [Configuration](#configuration)). **By default, these
settings are applied only to requests that the dashboard itself sends to Ollama** — its chat
UI, and the warm-load/restart/bulk-start "options" payloads (`app/routes/main.py`, e.g. the
`/api/models/start`, `/api/models/restart`, `/api/models/bulk/start`, and `/api/chat` handlers).

Ollama applies the `options` field strictly per HTTP request; it does not remember them for a
model afterwards. That means **any other client that talks to Ollama directly — the VS Code
Ollama extension, `ollama run`, `curl`, LangChain, etc. — will use Ollama's own defaults (or
whatever is baked into the model's `Modelfile`), not the values you saved here.** This is by
design (per-request `options` is the documented Ollama API behavior), but it surprises users
who expect "saved settings" to follow the model everywhere.

### Recommended: point external clients at the dashboard's built-in proxy (`/ollama/...`)

The dashboard exposes a settings-injecting proxy in `app/routes/proxy.py` — no extra process
required. Point a client's **base URL** at `http://<dashboard-host>:<port>/ollama` (default
port **5000**). Traffic is forwarded to the real Ollama backend (`OLLAMA_HOST` /
`OLLAMA_PORT`, usually `http://localhost:11434`).

**What gets your saved settings (`model_settings.json`)?**  
Settings are merged into the request `options` on **inference** calls (when Ollama loads or
runs the model for that request). Saved values **win** over whatever the client sent.

| Client route (via dashboard) | Upstream Ollama | Settings injected? |
|------------------------------|-----------------|-------------------|
| `POST /ollama/api/chat` | `/api/chat` | Yes |
| `POST /ollama/api/generate` | `/api/generate` | Yes |
| `POST /ollama/v1/chat/completions` | `/v1/chat/completions` (passthrough + settings) | Yes (**OpenAI-compatible clients**) |
| `POST /ollama/v1/completions` | `/api/generate` (bridged) | Yes |
| `GET /ollama/api/tags`, `GET /ollama/v1/models`, etc. | passthrough | No (list/show only) |

Ollama applies `options` **per request** — it does not remember them after unload. External
apps do **not** use the dashboard **Start** button; the first chat message loads the model
with your saved `num_ctx`, temperature, etc.

**OpenAI `/v1` note:** On some Ollama releases, raw `/v1/chat/completions` may not honor
every saved `options` field the same way as native `/api/chat`. The dashboard proxy merges
your saved settings, trims oversized prompts when enabled, and forwards compatible traffic.

#### Connect any external app (one address)

Use the dashboard as the **Ollama server address** or **API base URL** instead of
`http://localhost:11434`:

```text
http://<dashboard-host>:<port>/ollama
```

Examples (default port **5000**):

| App | Where to paste the address |
|-----|----------------------------|
| **Any Ollama-compatible tool** | Ollama server URL / host field |
| **OpenAI SDK** (`base_url`) | `http://127.0.0.1:5000/ollama/v1` |
| **VS Code — GitHub Copilot (Ollama)** | Ollama endpoint (no `/v1` suffix) |
| **Continue** | `apiBase` in config |
| **Claude Code / other IDE agents** | Ollama or model server URL field |
| **LangChain, curl, custom scripts** | Base URL pointing at `/ollama` |

**Dashboard UI:** click **Connect app** in the header for live checks and copy-paste URLs.

**VS Code (Copilot Ollama provider)** — optional setting:

```json
"github.copilot.chat.byok.ollamaEndpoint": "http://127.0.0.1:5000/ollama"
```

**Continue** example:

```jsonc
{ "models": [{ "title": "Local via dashboard", "provider": "ollama", "model": "qwen3.5:9b",
               "apiBase": "http://127.0.0.1:5000/ollama" }] }
```

**Verify the proxy before connecting apps:**

```text
http://127.0.0.1:5000/ollama/v1/models     → JSON model list
http://127.0.0.1:5000/ollama/api/tags      → JSON model list (native Ollama)
http://127.0.0.1:5000/ollama               → proxy health JSON
```

Both model-list URLs should return JSON, not an HTML error page. Restart the dashboard after upgrades.

Original model names are kept. **Every** saved option in `options` is applied — including
`presence_penalty`, `frequency_penalty`, `typical_p`, and `penalize_newline` (not valid in a
Modelfile). CORS for `/ollama/*` is open to any origin so IDE webviews can connect.

### Alternative: "Bake into Model" (for `ollama run` / clients you can't repoint)

If you can't change a client's base URL (e.g. plain `ollama run` from a terminal, or a tool
with no configurable endpoint) but want your saved values to follow a specific model, open
its **Settings** dialog and click **Bake into Model**. This calls `POST
/api/models/settings/<model>/bake`, which:

1. Generates a `Modelfile` with `FROM <model>` plus one `PARAMETER <key> <value>` line per
   saved setting that Ollama's Modelfile format supports (temperature, top_k, top_p, num_ctx,
   seed, num_predict, repeat_last_n, repeat_penalty, mirostat*, min_p, stop, etc.).
2. Calls Ollama's `/api/create` to build a new, derived model — named `<model>-dashboard`
   (e.g. `llama3-dashboard:8b`) — with those parameters baked in.

Run/reference the derived model name to get your saved defaults automatically — no proxy or
running dashboard required. Note that `presence_penalty`, `frequency_penalty`, `typical_p`,
and `penalize_newline` are **not** valid Modelfile `PARAMETER` directives, so they can't be
baked in this way (they're silently omitted from the generated `Modelfile`).

### Alternative: standalone proxy (`server_with_proxy.js`)

Runs as an independent Node process — useful if you want settings injection when the Flask
dashboard isn't running, or for **port takeover** on `:11434`. Reads the **same**
`model_settings.json` and injects settings on `/api/chat`, `/api/generate`, and
`/v1/chat/completions` (merged into `options` before forwarding). `/v1/completions` is also
accepted. Prefer the Flask dashboard proxy at `:5000/ollama` (adds `/ollama` prefix, CORS,
and settings merge for OpenAI-compatible clients).

```bash
npm install        # installs express + http-proxy-middleware
npm run proxy      # starts the proxy on http://localhost:11435 by default
```

Then point external clients at `http://localhost:11435` instead of Ollama's `:11434` (no
`/ollama` suffix needed — it mirrors Ollama's API directly at its root). Configure with env
vars (`OLLAMA_HOST`, `OLLAMA_PORT`, `MODEL_SETTINGS_FILE`, `PROXY_PORT`) if your setup differs
— see the comments at the top of `server_with_proxy.js`.

#### Zero-config variant: take over Ollama's default port

Repointing every client individually is tedious. Because this proxy mirrors Ollama's API at
its own root — unlike the dashboard's built-in proxy, which needs the `/ollama` prefix and so
can't do this — it can stand in for Ollama *at Ollama's own default address*. Every client that
already assumes Ollama lives at `localhost:11434` (VS Code extensions, `ollama run`, curl,
LangChain, ...) then gets your saved settings transparently, with **no client-side
configuration at all**:

1. **Relocate the real Ollama** off `:11434` — set `OLLAMA_HOST=127.0.0.1:11436` (Ollama's own
   combined `host:port` form for this variable) in the environment that *launches Ollama*, then
   restart Ollama so it picks up the change and starts listening on `:11436` instead.
2. **Run this proxy on the now-vacated `:11434`**, pointed at the relocated Ollama. On Windows,
   `start_proxy_takeover.bat` does both for you — sets `PROXY_PORT=11434` and runs `npm run
   proxy`, with pre-flight checks and guidance printed to the console. Manually: `set
   PROXY_PORT=11434&& set OLLAMA_HOST=127.0.0.1:11436&& npm run proxy`.

Using the combined `host:port` form means the **same** `OLLAMA_HOST` value configures Ollama,
the dashboard, *and* this proxy identically — all three split an embedded port out of
`OLLAMA_HOST` the same way (`_get_ollama_host_port()` /
`_normalize_ollama_host_port_for_display()` in the Python app, `resolveOllamaHostPort()` in
`server_with_proxy.js`), so there's nothing left to reconcile by hand.

To revert: stop the proxy, point `OLLAMA_HOST` back at Ollama's default (or remove the
override) and restart Ollama — it resumes listening on `:11434` directly, and every client
reaches it unchanged again (without saved-settings injection).

---

## Configuration

Configuration via environment variables:

```bash
OLLAMA_HOST=localhost              # Ollama hostname
OLLAMA_PORT=11434                  # Ollama port
AUTO_START_OLLAMA=true             # Start Ollama automatically if not already running

HISTORY_FILE=history.json          # Chat history file
MODEL_SETTINGS_FILE=model_settings.json
MAX_HISTORY=50                     # Max history entries

LOG_LEVEL=INFO                     # Logging level
```

`OLLAMA_HOST` may also be given in the combined `host:port` form — e.g.
`OLLAMA_HOST=127.0.0.1:11436` — which is the convention Ollama's *own* `OLLAMA_HOST` uses. An
embedded port wins over `OLLAMA_PORT`. This is normalized consistently everywhere the
dashboard talks to Ollama (including the `/ollama/api/...` proxy), so the same value also
configures `server_with_proxy.js`; see [Per-Model Settings: scope and
limitations](#per-model-settings-scope-and-limitations) for the deployment this enables.

`AUTO_START_OLLAMA` (default `true`) makes the dashboard check, on its own startup, whether
Ollama is already running — and start it itself if not, in a background thread so it never
delays the dashboard coming up. It tries (in order) the Windows `Ollama` service, common
install paths, then `ollama`/`ollama.exe serve` directly — see `_auto_start_ollama` /
`start_service` in `app/services/ollama_core.py` / `ollama_service_control.py`. This is the
*opposite direction* from `scripts/ollama-dashboard-monitor.ps1` (which watches **Ollama** and
starts/stops the **dashboard** accordingly — see [Deployment Guide](DEPLOYMENT.md)). Set
`AUTO_START_OLLAMA=false` if you'd rather always start Ollama yourself or via your own process
manager.

Create a `.env` file with your settings; defaults work out-of-the-box for local use.

---

## Background Updates

The service runs a background thread for:

| Data         | Interval | Notes                                                   |
| ------------ | -------- | ------------------------------------------------------- |
| System stats | 1s       | CPU, RAM, VRAM; cached for `/api/system/stats` (1s TTL) |
| Health ping  | ~15s     | Lightweight Ollama check for `/api/health` recovery     |

**Model list** (running and available) is **not** polled in the background; it is fetched when you load the page or click **Refresh**. The frontend polls system stats every 1s and health every 15s.

The background thread is automatically managed and restarts on crash.

---

## Development

### Testing

```bash
# Run all tests
python -m pytest -q

# Lint (same as CI lint job)
pip install ruff && ruff check app tests scripts

# Optional: same checks as tests/test_smoke_script.py (also run by pytest)
python scripts/smoke_check.py

# Run specific test
python -m pytest tests/test_start_model_pytest.py::test_start_model_success -q

# Coverage report
python -m pytest --cov=app --cov-report=html
```

CI runs `pytest -q` on Ubuntu and Windows; smoke checks run inside pytest via `tests/test_smoke_script.py` (see `.github/workflows/ci.yml`).

### Workflow

```bash
# After editing service/routes/UI:
1. python -m pytest -q
2. Restart the app
3. Test in browser: http://localhost:5000
```

---

## Troubleshooting

### Models show as "running" or "available" but list is wrong

- Click the **Refresh** button (next to "Available Models" or in the top bar) to refetch the model list
- Reload the page if needed

### Settings changes not persisting

- Check `model_settings.json` file permissions
- Ensure app directory is writable

### My saved parameters aren't used by external apps / `ollama run`

**If the client talks to Ollama directly** (`http://127.0.0.1:11434`), saved settings do
**not** apply — see [Per-Model Settings: scope and limitations](#per-model-settings-scope-and-limitations).

**If the client uses the dashboard proxy** (`http://127.0.0.1:5000/ollama`), settings apply
on each chat/generate request. Confirm
`http://127.0.0.1:5000/ollama/v1/models` returns JSON and the app's server/API address is
`http://127.0.0.1:5000/ollama` (not `:11434`). Raise **Context (num_ctx)** in the dashboard
and **Save** if an app reports context-size errors.

### Slow response times

- Check Ollama status: `curl http://localhost:11434/api/ps`
- Monitor system resources (CPU, RAM, VRAM, GPU 3D)

See [Troubleshooting](TROUBLESHOOTING.md) and [Architecture Guide](ARCHITECTURE.md) for more detail.

---

## Dependencies

```text
Flask==3.0.0           # Web framework
flask-cors==4.0.0      # CORS support
waitress==3.0.2        # Production WSGI server (Windows)
requests==2.31.0       # HTTP client
psutil==5.9.6          # System stats
pytz==2023.3           # Timezone support
```

Optional (for GPU monitoring):

```text
nvidia-ml-py           # VRAM monitoring (NVIDIA GPUs)
GPUtil                 # Alternative GPU stats
```

Docker uses Gunicorn (Linux) via `wsgi.py`; Windows bat files use Waitress.
