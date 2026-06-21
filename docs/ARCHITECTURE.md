# Ollama Dashboard Architecture Guide

## Overview

Ollama Dashboard is a Flask-based web interface for monitoring and controlling Ollama models. It's designed with clean separation of concerns and fail-safe operation.

### Design Principles
- **Single Responsibility**: Each service has one clear purpose
- **Dependency Injection**: Services receive dependencies; no global state
- **Fail-Safe**: Graceful degradation when Ollama is unavailable

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│            Browser / HTTP Client                    │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│        Flask Web Framework                          │
│  - HTTP routing & request/response handling         │
│  - Middleware (CORS, security headers)              │
│  - Served by Waitress (Windows) or Gunicorn (Linux) │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│        Route Layer                                  │
│  • app/routes/main.py — dashboard UI, /api/...      │
│  • app/routes/proxy.py — /ollama/... settings proxy │
│  • app/routes/api_proxy.py — Connect app, analytics, MCP status │
│  • app/routes/monitoring.py — /api/metrics/...      │
│  • /mcp — MCP Streamable HTTP (mounted on WSGI stack) │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│        Service Layer (app/services/)                │
│  ┌────────────────────────────────────────────────┐ │
│  │ OllamaService (main orchestrator)              │ │
│  │ Composes:                                      │ │
│  │  • OllamaServiceCore (caching, background)    │ │
│  │  • OllamaServiceModels (model operations)     │ │
│  │  • OllamaServiceControl (service control)     │ │
│  │  • OllamaServiceUtilities (settings, history) │ │
│  └────────────────────────────────────────────────┘ │
│                        ↓                             │
│  ┌────────────────────────────────────────────────┐ │
│  │ Supporting Components                          │ │
│  │  • TransientErrorDetector                      │ │
│  │  • PerformanceMetrics                          │ │
│  │  • RateLimiter (3 operation types)            │ │
│  └────────────────────────────────────────────────┘ │
│                        ↓                             │
│  ┌────────────────────────────────────────────────┐ │
│  │ External client proxy helpers                  │ │
│  │  • copilot_pipeline.py (orchestration)         │ │
│  │  • client_payload_compat.py (sanitize/cap)     │ │
│  │  • context_budget.py (auto-trim prompts)       │ │
│  │  • v1_native_bridge.py (OpenAI ↔ native)       │ │
│  │  • model_settings_helpers.py (merge options)   │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ MCP & Ask? agent                               │ │
│  │  • mcp_tools.py (shared tool registry)         │ │
│  │  • mcp_server.py (FastMCP → /mcp)              │ │
│  │  • ask_agent.py (server-side tool loop)        │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│        HTTP Client Layer (requests.Session)         │
│  - Connection pooling & keep-alive                  │
│  - Persistent session across requests               │
│  - Retry logic for transient errors                 │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│        Ollama API (localhost:11434)                 │
│  - /api/ps (running models)                        │
│  - /api/tags (available models)                    │
│  - /api/show (model details)                       │
│  - /api/generate (inference)                       │
│  - /api/pull (download)                            │
│  - /api/delete (remove)                            │
└─────────────────────────────────────────────────────┘
```

---

## Service Composition (Mixin Pattern)

The `OllamaService` class uses multiple inheritance (mixins) for clean separation:

```python
class OllamaService(
    OllamaServiceCore,      # Initialization, caching, background updates
    OllamaServiceModels,    # Model operations (start, stop, info, etc.)
    OllamaServiceControl,   # Service control (start Ollama, status checks)
    OllamaServiceUtilities  # Settings, history, persistence
):
    """Combines all functionality."""
```

### Method Resolution Order (MRO)
```python
OllamaService.__mro__ = (
    OllamaService,
    OllamaServiceCore,      # Base initialization
    OllamaServiceModels,    # Model-specific methods
    OllamaServiceControl,   # Service control methods
    OllamaServiceUtilities, # Utility/persistence methods
    object
)
```

### Each Mixin's Responsibility

#### OllamaServiceCore
- Service initialization with Flask app
- TTL-based caching (`_get_cached`, `_set_cached`)
- Background thread: system stats every 1s, health ping every ~15s
- Health component tracking
- History/settings loading

#### OllamaServiceModels
- Model listing (running, available, downloadable)
- Model info retrieval with capability detection
- System stats collection (CPU, RAM, VRAM, disk)
- Chat integration
- Model capabilities (vision, tools, reasoning)

#### OllamaServiceControl
- Service status checking (multi-platform: Windows, Linux, Mac)
- Service startup (multi-strategy: systemd, launchd, service.exe)
- Service stop/restart
- API verification

#### OllamaServiceUtilities
- History management (load/save)
- Model settings persistence (atomic JSON writes)
- Default settings generation (based on model size/capabilities)
- Chat session management
- Performance stats aggregation

---

## Data Flow Examples

### Example 1: Start Model
```
POST /api/models/start/llama3.1:8b
    ↓
route handler: start_model(model_name)
    ↓
validation: model_name must match pattern
    ↓
service: check if already running → POST /api/generate (keep_alive=24h)
    ├─ Retry up to 3x with exponential backoff if transient error
    ├─ Refresh running models cache on success
    └─ Return JSON response
```

### Example 2: Get System Stats
```
GET /api/system/stats
    ↓
service: ollama_service.get_system_stats()
    ├─ Check cache (ttl_seconds=5)
    ├─ If cached & fresh: return cached data
    ├─ If stale or missing:
    │  ├─ Collect system stats (CPU, RAM, disk)
    │  ├─ Get GPU VRAM (nvidia-ml-py, GPUtil, nvidia-smi fallback)
    │  └─ Cache result
    └─ Return JSON response
```

### Example 3: Save Model Settings
```
POST /api/models/settings/llama3.1:8b
    ↓
service: ollama_service.save_model_settings(model_name, settings)
    ├─ Acquire _model_settings_lock (thread-safe)
    ├─ Load current settings from model_settings.json
    ├─ Merge new settings
    ├─ Atomic write: write to .tmp, os.replace() to .json
    └─ Release lock
```

> **Application scope:** saving writes to `model_settings.json`. Settings are merged into
> outgoing request `options` by:
> - The dashboard itself — `app/routes/main.py` (`api_start_model`, `restart_model`,
>   `bulk_start_models`, `api_chat`, etc.).
> - External clients via the built-in proxy — `app/routes/proxy.py` (`/ollama/api/chat`,
>   `/ollama/api/generate`, `/ollama/v1/chat/completions`, `/ollama/v1/completions`).
>
> Ollama applies `options` per-request only. Clients on `:11434` directly never see saved
> values unless repointed at `http://<dashboard>:5000/ollama` or port-takeover proxy.
>
> **VS Code / GitHub Copilot:** base URL `http://127.0.0.1:5000/ollama`; chat hits
> `/ollama/v1/chat/completions`, which the proxy **bridges** to native `/api/chat` via
> `v1_native_bridge.py` with saved settings merged into `options` (including `num_ctx`).
> `client_payload_compat.py` sanitizes IDE payloads and caps output length. Model load
> happens on that inference request, not via dashboard Start. Model list uses
> `/ollama/api/tags` or `/ollama/v1/models` (passthrough, no settings).
>
> Three mechanisms for external clients (README
> [Per-Model Settings: scope and limitations](GUIDE.md#per-model-settings-scope-and-limitations)):
> 1. **Built-in proxy at `/ollama/...`** (`app/routes/proxy.py`) — merge via
>    `copilot_pipeline.py` + `client_payload_compat.py`; saved values win.
>    Native API; OpenAI `/v1/chat/completions` bridged to `/api/chat` (Copilot);
>    `/v1/completions` bridged via `v1_native_bridge.py`. Hop-by-hop upstream headers are
>    stripped so Waitress does not 500 on `/ollama/api/tags`.
> 2. **Bake into Model** — `OllamaServiceUtilities.bake_model_settings`.
> 3. **`scripts/proxy/server_with_proxy.js`** — same `data/model_settings.json`; mirrors API at proxy root;
>    merges settings on `/api/chat`, `/api/generate`, and `/v1/chat/completions`.
>
> **MCP tools server:** Streamable HTTP at `http://<dashboard>:5000/mcp` (same port as the UI).
> One registry in `mcp_tools.py` serves IDE MCP clients and Ask? agent mode (`POST
> /api/chat/agent`). The Ollama proxy forwards IDE *model* tool calls to Ollama; MCP exposes
> *dashboard* tools (list models, stats, etc.). See [GUIDE — MCP tools server](GUIDE.md#mcp-tools-server-mcp).

---

## MCP tools server

```text
Browser / Cursor / VS Code MCP client
        ↓
  http://<dashboard>:5000/mcp     ← Streamable HTTP (FastMCP + a2wsgi mount)
        ↓
  mcp_tools.execute_tool()        ← shared with Ask? agent loop
        ↓
  OllamaService → Ollama API
```

| Path | Role |
|------|------|
| `GET /api/mcp/status` | Tool catalog, health, URL for Connect UI |
| `POST /api/chat/agent` | Ask? agent mode — Ollama `/api/chat` + server-side tool execution |
| `/mcp` | MCP protocol for external IDEs |

Write tools (`start_model`, `stop_model`) require `MCP_ALLOW_WRITE=true`. Read tools are always available when MCP is mounted.

---

## Caching Strategy

| Data | TTL | Refresh | Purpose |
|------|-----|---------|---------|
| System stats | 1s | Background thread every 1s | CPU, RAM, VRAM for `/api/system/stats` |
| Health ping | — | Background thread every ~15s | Lightweight Ollama version check for recovery |
| Running models | On demand | Page load / Refresh button | Not polled in background |
| Available models | On demand | Page load / Refresh button | Not polled in background |
| Model info | 300s | On demand | Reduce repeated `/api/show` calls |
| Model settings | ∞ | On write | Persistent storage in JSON |
| Version | 300s | On demand | Ollama version rarely changes |

---

## Concurrency & Thread Safety

Shared `OllamaService` state is touched concurrently by **Waitress request threads** (8 by
default), the **background stats thread**, and the **`/api/show` enrichment pool** (≤3 workers).
CPython's GIL makes a *single* dict/deque operation atomic, but **compound** sequences
(check-then-act, value+timestamp pairs, `in` → `del`) are not — those need explicit locks.

### Background Thread
- **Runs in daemon mode** (exits when main thread exits)
- **Updates cycle**: System stats every 1s; Ollama health ping every ~15s
- **Model lists**: Fetched on page load or manual refresh only

### Locks & guards
| Primitive | Protects | Why |
|-----------|----------|-----|
| `_cache_lock` (`Lock`) | every read/write/clear of `_cache` + `_cache_timestamps` | keeps the value and its timestamp consistent; prevents TOCTOU `del` → `KeyError` and `dict changed size during iteration` |
| `_model_settings_lock` (`Lock`) | `_model_settings` writes + disk persistence | settings save is read-modify-write to a file |
| `_model_token_usage_lock` (`Lock`) | `_model_last_generate_tokens` | per-model token counters |
| `_history_lock` (`Lock`) | history deque snapshot/append | `list(self.history)` must not race `appendleft` |
| `_build_tls` (`threading.local`) | `get_available_models` re-entrancy depth | per-thread, so concurrent requests don't skip enrichment |
| `_stop_background` (`Event`) | background-thread shutdown signal | |

```python
def _set_cached(self, key, value):           # writer
    with self._cache_lock:
        self._cache[key] = value
        self._cache_timestamps[key] = datetime.now()

def _get_cached(self, key, ttl_seconds):      # reader: atomic value+timestamp read
    with self._cache_lock:
        ts = self._cache_timestamps.get(key)
        if not ts:
            return None
        if (datetime.now() - ts).total_seconds() < ttl_seconds:
            return self._cache.get(key)
        return None

def clear_cache(self, key):                   # pop, not "if in: del" (TOCTOU-safe)
    with self._cache_lock:
        self._cache.pop(key, None)
        self._cache_timestamps.pop(key, None)
```

> **Free-threaded builds (PEP 703, CPython 3.13+/3.14 `--disable-gil`):** the GIL no longer
> serializes individual dict ops, so these explicit locks are *required* for correctness, not
> just for compound invariants. The codebase runs on CPython 3.14; keep all `_cache`/history
> access behind the locks above.

History writes use an atomic temp-then-rename with a **per-process/thread** temp filename
(`history.json.<pid>.<tid>.tmp`) so concurrent saves never clobber a single shared temp file.

---

## Error Handling Strategy

### Transient Errors (Retry)
**Patterns**: Connection reset, timeout, forcibly closed, ECONNREFUSED, WSARECV, etc.

```python
for attempt in range(max_retries):
    try:
        response = self._session.post(...)
        return success_response
    except TransientError:
        if attempt < max_retries - 1:
            wait = 2 ** attempt  # 1s, 2s, 4s exponential backoff
            time.sleep(wait)
            continue
        return error_response
```

### Permanent Errors (Fail Fast)
**Patterns**: Not found, invalid, unauthorized, forbidden, no such file

---

## Health & Monitoring

### Component Health Checks
```python
health = ollama_service.get_component_health()
# Returns:
{
    "background_thread_alive": true,
    "cache_ages": {
        "running_models": 2.5,
        "available_models": 8.1
    },
    "failure_counters": {
        "consecutive_ps_failures": 0
    }
}
```

### Health Endpoints
- `GET /ping` — Lightweight health for orchestrators (Docker, K8s)
- `GET /health` — Simple health check
- `GET /api/health` — Detailed component health

---

## Quick Reference

### Starting the App

**Windows (production):**
```bash
start.bat
# Waitress on port 5000 — background process, no staying console
```

**Windows (development):**
```bash
start_dev.bat
# Flask debug reloader on port 5000
```

**Windows (stop / restart):**
```bash
stop_app.bat
restart_app.bat          # same mode as running instance
restart_app.bat dev      # force dev mode
```

**Development (Linux/macOS or pip install):**
```bash
pip install -r requirements.txt
python OllamaDashboard.py
# or: ollama-dashboard
```

**Docker (Linux, uses Gunicorn):**
```bash
docker-compose up -d
```

### Environment Configuration
```bash
export OLLAMA_HOST=localhost
export OLLAMA_PORT=11434

# OLLAMA_HOST may also be the combined "host:port" form — Ollama's own convention for
# this variable (an embedded port wins over OLLAMA_PORT). The dashboard, its built-in
# /ollama/api/... proxy, and server_with_proxy.js all split it out the same way, so one
# value configures everything consistently — see [GUIDE.md](GUIDE.md#per-model-settings-scope-and-limitations)
# for the port-takeover deployment this enables:
export OLLAMA_HOST=127.0.0.1:11436
```

### Checking Health
```bash
curl http://localhost:5000/api/health
```

---

## Troubleshooting

**Q: Models show as "running" but Ollama API returns 0 models**
A: Background thread cache is stale. Wait 10-15 seconds or restart the app.

**Q: Settings changes not persisting**
A: Check `model_settings.json` file permissions. Ensure app has write access.

**Q: High memory usage with many models**
A: Background thread caches full model info. Reduce cache size or increase TTL in `app/services/ollama_core.py`.

---

## Architecture Decision Records (ADRs)

### ADR-001: Mixin Composition over Inheritance
**Decision**: Use multiple inheritance (mixins) instead of deep inheritance chain.
**Rationale**: Flexibility, cleaner separation of concerns, easier testing.
**Trade-off**: MRO complexity, requires type checking blocks.

### ADR-002: In-Memory Cache over Database
**Decision**: Use Python dict with TTL instead of external database.
**Rationale**: Simplicity, no additional dependencies, sufficient for single-user / small team use.
**Trade-off**: Not distributed; lost on restart.

### ADR-003: Atomic File Writes for Settings
**Decision**: Write to `.tmp` file then `os.replace()` instead of direct write.
**Rationale**: Prevent corruption if process crashes mid-write.
**Trade-off**: Slightly slower; requires filesystem that supports atomic rename.

---

## References

- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Flask Documentation](https://flask.palletsprojects.com/)
