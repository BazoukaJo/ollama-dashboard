# Ollama Dashboard — API Reference

Consolidated HTTP surface for the dashboard web UI, REST API, Ollama proxy, and MCP tools server.

**Default base URL:** `http://127.0.0.1:5000` (configurable via server bind port).

**Conventions:**

- Many model endpoints accept the model name in the **path** (`/api/models/start/<model_name>`) or as a **query param** (`?model=` or `?name=`).
- List endpoints honor **`?refresh=1`** (or `true` / `yes`) to bypass cached Ollama catalog reads.
- JSON bodies are expected for `POST` / `DELETE` unless noted.
- Legacy `/api/copilot/*` routes mirror `/api/proxy/*` where listed.

---

## Dashboard UI

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/` | Main dashboard (HTML). Renders model cards, system stats, Connect panel. |
| GET | `/admin/model-defaults` | Admin page for model default settings (HTML). |

---

## Health & metrics

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/ping` | Lightweight liveness probe. Returns `{"status":"ok"}`. |
| GET | `/health` | Simple health: `ok` if background thread alive, else `degraded` (503). |
| GET | `/api/health` | Detailed component health (cache ages, failure counters, thread status). |
| GET | `/metrics` | Prometheus metrics (returns 501 — not enabled). |
| GET | `/api/metrics/performance` | Operation timing stats and success rates. |
| GET | `/api/metrics/rate-limits` | Remaining rate-limit quota per operation type. |
| GET | `/api/metrics/summary` | Combined health, performance, and rate-limit snapshot. |
| GET | `/api/test` | Smoke test — `{"message":"API is working"}`. |

---

## Models — list & info

| Method | Path | Query params | Description |
| ------ | ---- | ------------ | ----------- |
| GET | `/api/models/available` | `?refresh=1` | Installed models with settings flags and context metadata. |
| GET | `/api/models/running` | `?refresh=1` | Models currently loaded in Ollama memory. |
| GET | `/api/models/lists` | `?refresh=1` | Both running and available in one response. |
| GET | `/api/models/combined` | `?refresh=1` | One entry per model with `is_available` / `is_running` flags. |
| GET | `/api/models/derived` | — | Models created by **Bake into Model** (`*-dashboard` suffix). |
| GET | `/api/models/info/<model_name>` | — | Detailed metadata for one model tag. |
| GET | `/api/models/downloadable` | `?category=best` | Curated downloadable model catalog. |
| GET | `/api/models/memory/usage` | — | Memory usage for running models. |
| GET | `/api/models/performance/<model_name>` | — | Per-model performance metrics. |
| GET | `/api/version` | — | Ollama server version string. |

---

## Models — lifecycle

| Method | Path | Body / params | Description |
| ------ | ---- | ------------- | ----------- |
| POST | `/api/models/start/<model_name>` | — | Warm-start model into memory. |
| POST | `/api/models/start` | `?model=` | Same as above (query-param variant). |
| POST | `/api/models/stop/<model_name>` | Optional `{"force":true}` | Unload model (`keep_alive=0`). `force` restarts Ollama. |
| POST | `/api/models/stop` | `?model=` + optional body | Query-param variant. |
| POST | `/api/models/restart/<model_name>` | — | Stop then warm-start. |
| POST | `/api/models/restart` | `?model=` | Query-param variant. |
| POST | `/api/models/bulk/start` | `{"models":["name1","name2"]}` | Start multiple models. |
| DELETE | `/api/models/delete/<model_name>` | — | Delete model from disk and remove saved settings. |
| DELETE | `/api/models/delete` | `?model=` | Query-param variant. |
| POST | `/api/models/pull/<model_name>` | — | Pull model from registry. |
| POST | `/api/models/pull` | `?model=` & `?stream=true` | Pull with optional SSE progress stream. |

Rate-limited: start, stop, restart, delete, bulk start, benchmark (not pull).

---

## Models — settings

| Method | Path | Body / params | Description |
| ------ | ---- | ------------- | ----------- |
| GET | `/api/models/settings/<model_name>` | — | Saved settings for one model. |
| GET | `/api/models/settings` | `?model=` | Query-param variant. |
| GET | `/api/models/settings/recommended/<model_name>` | — | Hardware-aware recommended settings. |
| GET | `/api/models/settings/recommended` | `?model=` | Query-param variant. |
| POST | `/api/models/settings/<model_name>` | Settings JSON (+ optional `client` block) | Save per-model settings. |
| POST | `/api/models/settings` | `?model=` + body | Query-param variant. |
| DELETE | `/api/models/settings/<model_name>` | — | Remove saved settings. |
| DELETE | `/api/models/settings` | `?model=` | Query-param variant. |
| POST | `/api/models/settings/<model_name>/bake` | — | Bake settings into a derived Modelfile. |
| POST | `/api/models/settings/bake` | `?model=` | Query-param variant. |
| POST | `/api/models/settings/<model_name>/reset` | — | Reset to recommended defaults. |
| POST | `/api/models/settings/reset` | `?model=` | Query-param variant. |
| POST | `/api/models/settings/migrate` | — | Deprecated (410). |
| POST | `/api/models/settings/apply_all_recommended` | — | Apply recommended settings to all non-user-saved models. |
| POST | `/api/models/settings/copy` | `{"from":"src","to":"dst"}` | Copy settings between model names. |
| GET | `/api/models/settings/export` | `?model=` (optional) | Export all or one model's settings. |
| POST | `/api/models/settings/import` | `{"settings":{...}}` | Import settings entries. |

---

## Models — benchmark

Objective 8-prompt suite (reasoning, coding, knowledge, instruction, creativity, speed) with scored results and tuning advice.

| Method | Path | Body | Description |
| ------ | ---- | ---- | ----------- |
| POST | `/api/models/benchmark` | Optional `{"models":["name1"],"compare":true,"async":true}` | Benchmark all or selected models. With `"compare":true`, also includes `baseline` and `proxy_advantage`. With `"async":true`, returns `task_id` — poll `GET /api/tasks/<id>`. |
| POST | `/api/models/benchmark/tune` | Optional `{"max_rounds":3,"models":[…]}` | Multi-round benchmark → apply tuning → re-test (background). Returns `task_id`. |
| POST | `/api/models/benchmark/<model_name>` | Optional `{"compare":true}` | Benchmark one model; with compare, returns `dashboard`, `baseline`, `advantage`, and `improvements`. |

**Task status (long operations)**

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/tasks` | Recent background tasks (benchmark, tune loop). |
| GET | `/api/tasks/<task_id>` | Poll progress: `state`, `percent`, `message`, `result`. |

**CLI**

- Full fleet + proxy lift + improvements: `python scripts/run_dual_benchmark.py` → `data/dual_benchmark_results.json`
- Multi-round tune loop: `python scripts/benchmark_tune_loop.py` → `data/benchmark_tune_history.json`
- Apply `suggested_settings` from a report and re-test: `python scripts/apply_benchmark_improvements.py`

**Response fields (`improvements`)**

| Field | Meaning |
| ----- | ------- |
| `validation.status` | `ok`, `needs_tuning`, or `critical` |
| `suggested_settings` | e.g. raise `num_ctx` / `num_predict` |
| `suggested_client` | e.g. `context_trim_enabled`, `copilot_think` |
| `agentic` | Roles, proxy URL, keep-alive, long-session communication tips |

Rate-limited with other model operations.


## Models — residency

Pin a **fast** model (always in RAM) plus optional **heavy** model for dual-tier inference on
64 GB+ systems. Requires Ollama server env `OLLAMA_MAX_LOADED_MODELS=2` (see [GUIDE](GUIDE.md)).

| Method | Path | Body | Description |
| ------ | ---- | ---- | ----------- |
| GET | `/api/residency/status` | — | Pin registry merged with Ollama `/api/ps`; includes `resident_fast_loaded`, `resident_heavy_loaded`, and suggested Ollama server env. |
| POST | `/api/residency/pin` | `{"model":"gemma4:latest","role":"fast","keep_alive":-1}` | Load and pin a model. `{"model":"…","unpin":true}` removes from pin registry. |

Stopping a pinned model: `POST /api/models/stop/<model>` with `{"unpin": true}` or `{"force": true}`.

Proxy status (`GET /api/proxy/status`) includes `resident_fast_model`, `pinned_models`, etc.


## Chat

| Method | Path | Body | Description |
| ------ | ---- | ---- | ----------- |
| POST | `/api/chat` | `{"model":"…","messages":[…],"stream":false}` | Multi-turn chat via Ollama `/api/chat`. Supports attachments on latest user turn. |
| POST | `/api/chat/agent` | Same shape | **Ask? agent mode** — server-side tool loop (NDJSON stream). Requires tool-capable model. |
| GET | `/api/chat/history` | — | List saved chat sessions. |
| POST | `/api/chat/history` | Session JSON (max 1 MB) | Save a chat session. |
| DELETE | `/api/chat/history/<session_id>` | — | Delete one session. |
| DELETE | `/api/chat/history` | — | Clear all sessions. |

---

## System stats

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/system/stats` | Current CPU, RAM, VRAM, disk snapshot. |
| GET | `/api/system/stats/history` | Historical stats for dashboard sparklines. |

---

## Service control

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/api/service/status` | Ollama service running/stopped status. |
| POST | `/api/service/start` | Start Ollama service. |
| POST | `/api/service/stop` | Stop Ollama service. |
| POST | `/api/service/restart` | Restart Ollama service. |
| POST | `/api/service/update-ollama` | Platform upgrade (winget/brew/install.sh) then restart. |
| POST | `/api/service/install-ollama` | Install Ollama when not detected, then start. |
| POST | `/api/full/restart` | Restart dashboard caches and background thread (not Ollama). |
| POST | `/api/force_kill` | Force-kill dashboard process and child processes. |

---

## Proxy — status & setup

| Method | Path | Query params | Description |
| ------ | ---- | ------------ | ----------- |
| GET | `/api/proxy/status` | — | Proxy activity summary for dashboard header. Legacy: `/api/copilot/status`. |
| GET | `/api/proxy/wizard-checks` | — | Connect wizard self-checks and client example snippets. Legacy: `/api/copilot/wizard-checks`. |
| GET | `/api/proxy/analytics` | — | Proxy usage analytics. Legacy: `/api/copilot/analytics`. |
| GET | `/api/proxy/debug-requests` | `?limit=20` (max 100) | Recent proxied chat requests from log. Legacy: `/api/copilot/debug-requests`. |
| POST | `/api/proxy/prewarm` | `{"model":"…"}` | Schedule background context preload. Legacy: `/api/copilot/prewarm`. |
| GET | `/api/advisor/recommend` | `?model=` (optional) | Hardware-based model/context recommendations. |

**Proxy base URL:** `http://127.0.0.1:5000/ollama`  
**OpenAI-compatible base URL:** `http://127.0.0.1:5000/ollama/v1`

---

## Proxy — Ollama routes (`/ollama/...`)

Settings from `model_settings.json` are merged into **inference** requests (chat, generate, completions). List/show routes pass through unchanged.

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/ollama` | Proxy health JSON and usage hint. |
| GET | `/ollama/proxy-debug` | Recent proxy log lines (local troubleshooting). Legacy: `/ollama/copilot-debug`. |
| POST | `/ollama/api/chat` | Native Ollama chat with settings injection. |
| POST | `/ollama/api/generate` | Native Ollama generate with settings injection. |
| GET, POST, PUT, DELETE | `/ollama/api/<path>` | Passthrough to Ollama `/api/<path>` (e.g. `tags`, `show`, `pull`, `ps`). |
| POST | `/ollama/v1/chat/completions` | OpenAI-compatible chat (bridged to `/api/chat`). Legacy alias: `/ollama/chat/completions`. |
| POST | `/ollama/v1/completions` | OpenAI completions (bridged to `/api/generate`). |
| GET, POST, PUT, DELETE | `/ollama/v1/<path>` | Passthrough to Ollama `/v1/<path>` (e.g. `models`). |

All proxy routes accept `OPTIONS` for CORS preflight.

**Verify:**

```text
GET  http://127.0.0.1:5000/ollama/v1/models
GET  http://127.0.0.1:5000/ollama/api/tags
GET  http://127.0.0.1:5000/ollama
```

---

## MCP

| Method | Path | Description |
| ------ | ---- | ----------- |
| * | `/mcp` | MCP Streamable HTTP server (tools). Same port as dashboard; not a Flask route. |
| GET | `/api/mcp/status` | MCP health, tool catalog, and `mcp_base_url`. |

**MCP base URL:** `http://127.0.0.1:5000/mcp`

Default read-only tools: `list_available_models`, `list_running_models`, `get_model_info`, `get_system_stats`, `get_proxy_status`, `prewarm_model`. Optional write tools (`start_model`, `stop_model`) when `MCP_ALLOW_WRITE=true`.

**Cursor config** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "ollama-dashboard": {
      "url": "http://127.0.0.1:5000/mcp"
    }
  }
}
```

Use `python scripts/setup_cursor.py` for one-step MCP (and optional model override) setup — see [GUIDE.md](GUIDE.md).

---

## RAG (optional)

| Method | Path | Body | Description |
| ------ | ---- | ---- | ----------- |
| GET | `/api/rag/status` | — | RAG index status. |
| POST | `/api/rag/index` | `{"root":"/path"}` | Index workspace (requires `RAG_ENABLED=true`). |

---

## Related docs

- [GUIDE.md](GUIDE.md) — setup, Connect wizard, environment variables
- [ARCHITECTURE.md](ARCHITECTURE.md) — proxy bridge, MCP implementation
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — common client connection issues
