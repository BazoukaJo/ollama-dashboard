# Ollama Dashboard — Complete Guide

Detailed setup, configuration, proxy and MCP integration, and development reference. For a quick start, see the [README](../README.md).

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
| `POST /ollama/v1/chat/completions` | `/api/chat` (bridged) | Yes (**OpenAI-compatible clients**) |
| `POST /ollama/v1/completions` | `/api/generate` (bridged) | Yes |
| `GET /ollama/api/tags`, `GET /ollama/v1/models`, etc. | passthrough | No (list/show only) |

Ollama applies `options` **per request** — it does not remember them after unload. External
apps do **not** use the dashboard **Start** button; the first chat message loads the model
with your saved `num_ctx`, temperature, etc.

**OpenAI `/v1` note:** OpenAI-compatible chat (VS Code Copilot, Continue, OpenAI SDKs) is
**bridged to native `/api/chat`** so saved `num_ctx` and other `options` are honored. The
proxy also sanitizes unsupported OpenAI fields, maps `max_completion_tokens` → `max_tokens`,
caps output length for IDE clients, and auto-trims oversized prompts when enabled.

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

### VS Code Copilot (Ollama)

**VS Code 1.122+ (recommended).** GitHub Copilot Chat's built-in BYOK ships an **Ollama /
Custom Endpoint** provider. Point it at the dashboard proxy:

1. `Ctrl+Shift+P` → **Chat: Manage Language Models** → **Add** → **Ollama**.
2. Enter the endpoint **`http://127.0.0.1:5000/ollama`** (the dashboard proxy — not `:11434`).
3. Select a dashboard model in Copilot Chat.

VS Code stores providers in **`chatLanguageModels.json`** (next to `settings.json`):

```json
[
  { "name": "OllamaDashboard", "vendor": "ollama", "url": "http://127.0.0.1:5000/ollama" }
]
```

**One-step setup:** from the repo root, run the helper — it writes the provider entry plus a few
context-reduction settings (`chat.tools.compressOutput.enabled`, `files.exclude`), with a backup:

```bash
python scripts/setup_vscode.py
# options: --port 5000 | --endpoint <url> | --insiders | --dry-run
```

> **Legacy (pre-1.122):** older builds used the User Settings key
> `"github.copilot.chat.byok.ollamaEndpoint": "http://127.0.0.1:5000/ollama"`. It is
> **deprecated and silently removed** on current VS Code, so use the provider above instead.

There is **no VS Code setting** to change how long Copilot waits for Ollama responses; request
timeouts are fixed inside the extension. If chat fails on cold start or large models, pre-start
the model in the dashboard and see
[TROUBLESHOOTING.md — VS Code Copilot: request timeout](TROUBLESHOOTING.md#vs-code-copilot-request-timeout-or-model-wont-load).

**Agent mode:** Copilot Agent sends tool definitions on every request. The dashboard proxy
forwards those tools to native `/api/chat` and streams `tool_calls` back in OpenAI SSE shape.
Use a model Ollama lists with tool support (for example Qwen3, gemma4, or Llama 3.1+). Agent /
tool turns always run with thinking **off** so reasoning tokens never corrupt the tool exchange.

**Reasoning / thinking models (gemma4, qwen3):** Copilot BYOK renders `delta.content` only and
ignores `delta.reasoning`, so by default plain chat runs with `think: false` (you would otherwise
see a lone `I` and "Sorry, no response was returned"). To actually use a model's reasoning in
Copilot, open the model's **Settings** in the dashboard and set **Reasoning for external clients
(Copilot)**:

| Mode | Behavior (plain chat) |
|------|-----------------------|
| **Off** (default) | Force `think: false` — fast, direct answers. |
| **Auto** | Follow the client's reasoning request (Copilot's `reasoning_effort`), else off. |
| **On** | Always think; the reasoning is **mirrored into the visible answer** since Copilot only renders content. |

This is a per-model setting saved under the model's `client` block. The legacy environment
variable `OLLAMA_COPILOT_ALLOW_THINKING=true` still works as a global **Auto** default.

**Large models that exceed VRAM** (e.g. `gemma4:31b` ~20 GB, `qwen3.6:35b` ~24 GB on a 16 GB
GPU): Ollama transparently offloads the overflow to system RAM, so the first request is slow
(30–90 s cold load) — the proxy holds the connection open with SSE heartbeats so VS Code does not
time out. These models support a 256K context; the dashboard's recommended `num_ctx` stays
conservative for speed, but if you have spare system RAM you can raise **Context (num_ctx)** in
the model's Settings and the proxy will honor it (it bridges to native `/api/chat`).

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

### MCP tools server (`/mcp`)

The dashboard also exposes a **Model Context Protocol (MCP)** server on the **same port** as the
web UI. IDE agents (Cursor, VS Code MCP extension) can connect to dashboard tools — list models,
read system stats, check proxy activity — without scraping the web UI.

```text
http://<dashboard-host>:<port>/mcp
```

Default: **`http://127.0.0.1:5000/mcp`**

This is **separate from the Ollama proxy** above:

| Connection | URL | Purpose |
|------------|-----|---------|
| **Ollama proxy** | `http://127.0.0.1:5000/ollama` | LLM inference (chat, completions) with saved settings |
| **MCP tools** | `http://127.0.0.1:5000/mcp` | Dashboard tools (models, stats, proxy status) |

Use **both** in Cursor or VS Code: proxy for the model, MCP for dashboard actions.

**Dashboard UI:** open **Connect** in the header — the wizard shows the MCP URL, a tool catalog,
and copy-paste JSON for Cursor (`.cursor/mcp.json`) and VS Code.

**Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "ollama-dashboard": {
      "url": "http://127.0.0.1:5000/mcp"
    }
  }
}
```

**VS Code** (MCP extension / settings JSON — exact key depends on your extension):

```json
{
  "servers": {
    "ollama-dashboard": {
      "type": "http",
      "url": "http://127.0.0.1:5000/mcp"
    }
  }
}
```

**Available tools (read-only by default):**

| Tool | Description |
|------|-------------|
| `list_available_models` | Installed models and capability flags |
| `list_running_models` | Models loaded in Ollama memory |
| `get_model_info` | Metadata for one model tag |
| `get_system_stats` | CPU, RAM, VRAM snapshot |
| `get_proxy_status` | External IDE proxy activity |

Optional **write** tools (`start_model`, `stop_model`) are off unless you set
`MCP_ALLOW_WRITE=true` and restart the dashboard.

**Ask? agent mode:** On the dashboard, **Ask?** on a model with **tool support** (`has_tools`)
automatically uses the same tool registry via `POST /api/chat/agent` (server-side tool loop).
The modal shows an **Agent mode** badge and live tool steps. Plain models still use
`POST /api/chat` → Ollama `/api/generate` without tools.

**Verify MCP:**

```text
GET http://127.0.0.1:5000/api/mcp/status   → JSON (URL, tool count, health)
```

The Connect wizard also runs an `mcp_endpoint` check.

**MCP environment variables (optional):**

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_ALLOW_WRITE` | `false` | Set `true` to expose `start_model` / `stop_model` |
| `ASK_AGENT_MAX_ITERATIONS` | `8` | Max tool rounds per Ask? agent request (1–20) |

Implementation: `app/services/mcp_tools.py` (shared registry),
`app/services/mcp_server.py` (Streamable HTTP at `/mcp`),
`app/services/ask_agent.py` (Ask? tool loop). See [Architecture](ARCHITECTURE.md#mcp-tools-server).

**Proxy environment variables (optional):**

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_PROXY_MAX_PREDICT` | `8192` | Max output tokens for external clients (plain chat); raise up to 16384 for longer answers |
| `OLLAMA_PROXY_MAX_PREDICT_AGENT` | `32768` | Max output tokens for agent/tool turns (long edits) |
| `OLLAMA_COPILOT_ALLOW_THINKING` | `false` | Global default for **Auto** reasoning (per-model **Reasoning** setting overrides) |
| `OLLAMA_PROXY_MAX_RESPONSE_CHARS` | `96000` | Max chars in non-streaming responses returned to IDEs |
| `OLLAMA_PROXY_STREAM_HEARTBEAT_SECONDS` | `10` | Idle seconds before sending an SSE keep-alive comment while a model loads/stalls (keeps VS Code Copilot from timing out on cold loads) |
| `OLLAMA_PROXY_STREAM_FIRST_BYTE_GRACE_SECONDS` | `3` | Seconds to wait for a fast upstream error before committing the keep-alive stream |
| `OLLAMA_V1_PASSTHROUGH` | `false` | Set `true` to forward `/v1/chat/completions` to Ollama `/v1` instead of bridging to `/api/chat` |
| `CONTEXT_TRIM_ENABLED` | `true` | Auto-trim long prompts to fit `num_ctx` |
| `OLLAMA_COPILOT_PRELOAD_CTX` | `true` | Preload model context before first v1 chat request |

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

### Alternative: standalone proxy (`scripts/proxy/server_with_proxy.js`)

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
   `scripts\start_proxy_takeover.bat` does both for you — sets `PROXY_PORT=11434` and runs `npm run
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

HISTORY_FILE=data/history.json          # Model-list snapshot history (not chat sessions)
MODEL_SETTINGS_FILE=data/model_settings.json
MAX_HISTORY=50                     # Max model-list history entries

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

**Persistence files** (written next to `HISTORY_FILE` unless paths are absolute):

| File | Purpose |
|------|---------|
| `data/history.json` | Rolling model-list snapshots (`MAX_HISTORY`, default 50) |
| `data/chat_history.json` | Ask? chat sessions (max 100) |
| `data/model_settings.json` | Per-model saved settings |
| `data/system_stats_history.json` | Sparkline data for system metrics |

---

## Windows: start, stop, and restart

The dashboard ships batch scripts that share one process manager:
`scripts/dashboard-process.ps1`. It detects dashboard processes by **command line and repo
path**, not just "whatever is on port 5000".

| Script | Mode | Server |
|--------|------|--------|
| `start.bat` | **release** | Waitress (`wsgi:app`) — background, no staying terminal |
| `start_dev.bat` | **dev** | Flask debug reloader — visible console |
| `stop_app.bat` | — | Stops dashboard instance; refuses to kill foreign apps on port 5000 |
| `restart_app.bat` | auto | Restarts in the **currently running** mode (or saved mode if stopped) |

**Examples:**

```bat
start.bat                  REM production
start_dev.bat              REM development with auto-reload
stop_app.bat               REM stop whatever dashboard is running
restart_app.bat            REM restart same mode
restart_app.bat dev        REM force restart in dev mode
restart_app.bat release    REM force restart in release mode
```

**Behavior:**

- `start.bat` / `start_dev.bat` check port 5000 first. If the **same** mode is already
  running, they report it and exit. If the **other** mode is running, they stop it and start
  the requested mode.
- **Release** (`start.bat`) starts Waitress as a hidden background process. Startup and server
  logs go to `data\dashboard-release-launch.log` and `data\dashboard-release-error.log`. Use
  `start.bat console` for a visible launcher when troubleshooting.
- **Development** (`start_dev.bat`) keeps a console open with Flask debug output.
- `restart_app.bat` detects the live process mode (`release`, `dev`, or `cli` from
  `ollama_dashboard_cli.py`) before choosing which start script to open.
- `data\dashboard.run-mode` records the last started mode (`release` or `dev`) as a fallback
  when nothing is running.

**Check status manually:**

```powershell
powershell -File scripts\dashboard-process.ps1 -Action status
```

Exit code `0` = dashboard running; `1` = not running; `4` = port blocked by a non-dashboard
process.

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
2. Restart the app (restart_app.bat on Windows, or stop + start)
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
pypdf>=4.0.0           # PDF text extraction (Ask? attachments)
python-docx>=1.1.0     # DOCX text extraction (Ask? attachments)
mcp>=1.27,<2           # MCP tools server (/mcp)
a2wsgi>=1.10.0         # Mount MCP ASGI on same port as Flask
```

Optional (for GPU monitoring):

```text
nvidia-ml-py           # VRAM monitoring (NVIDIA GPUs)
GPUtil                 # Alternative GPU stats
```

Docker uses Gunicorn (Linux) via `wsgi.py`; Windows bat files use Waitress.
