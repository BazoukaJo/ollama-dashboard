# Troubleshooting

Quick checks when the dashboard misbehaves. No new features required—just isolation.

## Running models empty, but Ollama has a loaded model

1. **Same server** — The dashboard uses `OLLAMA_HOST` and `OLLAMA_PORT` (default `localhost:11434`). Confirm with the header chip on the dashboard vs where you run `ollama ps`.
2. **CLI vs API** — Run `curl -s http://127.0.0.1:11434/api/ps` (or your host/port). If that JSON shows `models: []`, Ollama itself reports nothing loaded; the UI is correct.
3. **Timing** — After starting a model, wait a second and use **Refresh** or let the countdown run; `/api/ps` can lag briefly right after load.
4. **Firewall / Docker** — If Ollama is in another container, `localhost` from the dashboard container is wrong; point `OLLAMA_HOST` at the service name or `host.docker.internal`.

## Settings modal: JSON error or 404

1. **Library-style names** — Names like `user/model:tag` must use the dashboard’s query-based settings API (the current UI does this). If you call the API manually, prefer `GET /api/models/settings?model=...` (URL-encoded).
2. **Auth** — With `ENABLE_AUTH=true`, settings mutations need an operator API key; missing auth returns 401 JSON, not HTML.

## Install / update Ollama (Windows) looked wrong but worked

The app treats **Ollama’s HTTP API as the source of truth** after install/update. Winget and Chocolatey sometimes return non-zero exit codes when the install actually succeeded. Check **Ollama version** in the header and `ollama --version` in a terminal.

## My saved per-model settings aren't used by VS Code / `ollama run` / other tools

By default, this is expected when clients talk to Ollama **directly** at `:11434`. The
dashboard merges saved settings into the `options` field of requests **it sends itself**
(chat, warm-load, restart, bulk-start — `app/routes/main.py`). Ollama applies `options`
strictly per-request and never stores them against the model.

### Using the dashboard proxy (recommended for VS Code / Copilot)

Point the client at **`http://<dashboard-host>:<port>/ollama`** (e.g.
`http://127.0.0.1:5000/ollama`). The proxy in `app/routes/proxy.py` forwards to Ollama and
merges saved settings on **inference** routes:

| Via dashboard | Settings? |
|---------------|-----------|
| `POST /ollama/v1/chat/completions` | Yes — **GitHub Copilot Chat** |
| `POST /ollama/api/chat`, `/ollama/api/generate` | Yes |
| `GET /ollama/api/tags`, `GET /ollama/v1/models` | No (model listing only) |

Copilot does **not** call the dashboard **Start model** API; the first chat message loads the
model. The proxy bridges `/ollama/v1/chat/completions` to native `/api/chat` so saved
`num_ctx` applies (Ollama's raw `/v1/...` endpoint ignores `options.num_ctx`).

**GitHub Copilot setup:**

1. Dashboard running on port 5000 (or your port).
2. Ollama endpoint: `http://127.0.0.1:5000/ollama` — **do not** add `/v1` (Copilot appends
   `/v1/chat/completions`).
3. Setting: `"github.copilot.chat.byok.ollamaEndpoint": "http://127.0.0.1:5000/ollama"`.
4. Save settings per model in the dashboard UI.

**Verify:**

```text
http://127.0.0.1:5000/ollama/v1/models
http://127.0.0.1:5000/ollama/api/tags
```

Both must return JSON. HTML 404/500 means restart the dashboard after an upgrade.

> **Historical bug (2026-06-07):** `/ollama/api/...` merged the whole stored entry instead of
> just `settings`; fixed in `app/routes/proxy.py`. Another bug double-ported `OLLAMA_HOST`
> when it carried `host:port`.

Three ways to get saved settings to external clients — see the README's
[Per-Model Settings: scope and limitations](../README.md#per-model-settings-scope-and-limitations)
for full details:

1. **Point the client at the dashboard's built-in proxy** — base URL
   `http://<dashboard-host>:<port>/ollama`. Covers native `/api/...` and OpenAI-compatible
   `/v1/chat/completions` (Copilot).
2. **Bake into Model** (Settings dialog button) — derived model name for clients you can't
   repoint.
3. **Run `server_with_proxy.js`** — same injection at the proxy root (port takeover on
   `:11434`). Merges settings on `/api/chat`, `/api/generate`, and `/v1/chat/completions`.
   For Copilot, the Flask dashboard proxy at `:5000/ollama` is still recommended (CORS + `/ollama` prefix).

## Port-takeover proxy: nothing answers at `:11434`, or it won't start

This applies only if you've set up the [zero-config "port takeover" variant](../README.md#per-model-settings-scope-and-limitations)
of `server_with_proxy.js` — relocating Ollama via `OLLAMA_HOST=host:port` and running the proxy
with `PROXY_PORT=11434` (e.g. via `start_proxy_takeover.bat`).

- **Nothing answers at `:11434` / every client reports "Ollama not running"**: the takeover
  proxy isn't running (it crashed, or you haven't started it yet this session). Start it
  (`start_proxy_takeover.bat`, or `npm run proxy` with `PROXY_PORT=11434`) — or see "Revert"
  below to get back to a plain setup immediately.
- **Proxy fails to start — `EADDRINUSE` / "port already in use"**: something is still bound to
  `:11434`, almost always the real Ollama because it hasn't actually been relocated yet.
  Confirm `OLLAMA_HOST` is set to the combined `host:port` form (e.g. `127.0.0.1:11436`) **in
  the environment that launches Ollama** (not just the proxy's), and that Ollama has been
  *restarted* since — it only re-reads `OLLAMA_HOST` at startup. To see who's holding the
  port: `netstat -aon | findstr :11434` (Windows), then check the PID's process name —
  `ollama.exe` / `ollama app.exe` means Ollama is still on its default port.
- **Proxy starts, but every request fails or times out**: it's listening but can't reach the
  relocated Ollama. The proxy prints its forwarding target on startup ("Forwarding to Ollama
  at: ...") — confirm that address matches where Ollama now actually listens (e.g. test it
  directly: `curl http://127.0.0.1:11436/api/tags`).

**Revert to a plain setup** (no proxy in front of Ollama, no settings injection): stop the
proxy, point `OLLAMA_HOST` back at Ollama's default — or remove the override entirely — and
restart Ollama. It resumes listening on `:11434` directly, and every client reaches it
unchanged.

## VS Code / Copilot / IDE: `exceed_context_size_error` (8192 tokens)

Symptoms: VS Code reports a 400 like:

```text
request (31995 tokens) exceeds the available context size (8192 tokens)
```

**Cause:** Ollama's context window for that request is **8192** (`num_ctx`), but the IDE
sent a much larger prompt (open files + chat history). **8192 is only the dashboard default**
— your **saved** per-model settings override it once you change and save Context in the
dashboard (or via `model_settings.json`).

If you use the dashboard proxy (`http://<host>:5000/ollama`) or port-takeover proxy
(`:11434`), saved settings — including `num_ctx` — are merged into every IDE request.

**Fix:**

1. Open the model's **Settings** in the dashboard → **Context (num_ctx)** → set to what
   the model supports (e.g. **32768** or **131072**) → **Save**.
2. Restart the dashboard / Node proxy if running, then retry in VS Code.
3. Alternatively, point the IDE at Ollama directly and set context in the extension, or
   reduce how much workspace context the extension includes.

Until you save a higher `num_ctx`, the default **8192** applies — which is too small for
typical VS Code prompts (~20k–100k tokens).

**Allocated context shows 4096/8192 but Settings shows more:** The **Allocated** column is
what Ollama actually loaded (`/api/ps`), not what you saved. Common causes:

1. **Model already in memory** — Ollama keeps the context size from the *first* load. Use
   **Restart model** on the dashboard card, or stop the model, then send a new Copilot message
   through `:5000/ollama`.
2. **Bypassing the proxy** — Copilot or another client pointed at `:11434` directly never
   gets dashboard settings.
3. **Raw Ollama v1** — Even with merged `options`, Ollama's `/v1/chat/completions` ignores
   `num_ctx`; the dashboard bridges v1 chat to `/api/chat` so saved context applies.

**Copilot loads model at 4K despite saved 40K context:** Confirm endpoint is
`:5000/ollama`, restart the dashboard, **restart/stop the model**, then send a new Copilot
message.

**"Sorry, no response was returned" in Copilot Chat:** Usually means Copilot received an
empty or malformed stream. After upgrading the dashboard, **restart** it (`restart_app.bat`),
start a **new chat**, and confirm `http://127.0.0.1:5000/ollama/v1/models` returns JSON.
Recent builds passthrough `/ollama/v1/chat/completions` to Ollama's native v1 endpoint (required
for reasoning models and Agent-mode tool calls). If it persists, try **Ask** mode first, then
check Copilot Chat diagnostics for the underlying HTTP error.

**404 HTML "Not Found" in Copilot Chat:** GitHub Copilot sends chat to
`POST {baseUrl}/v1/chat/completions`, not `/api/chat`. The dashboard proxy must expose
`/ollama/v1/...` (added in recent builds). After updating, restart the dashboard and
confirm:

```text
http://127.0.0.1:5000/ollama/v1/models
```

returns JSON (not an HTML 404 page). VS Code Ollama base URL stays
`http://127.0.0.1:5000/ollama` (no `/v1` suffix — Copilot adds `/v1/chat/completions`).

## `model_settings.json` corrupted or empty

- The file lives under the process working directory by default, or set `MODEL_SETTINGS_FILE` to an absolute path.
- Writes use a **temporary file + atomic replace**; if the file is corrupt, restore from backup or delete it to recreate defaults (per-model entries will be rebuilt as you use models).

## Logging

Set `LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, or `ERROR` (default `INFO`) before starting the app to tune console verbosity.

## Ollama version

The dashboard is tested against **recent Ollama releases**; very old servers may differ in `/api/ps` or `/api/show` shape. Upgrade Ollama if endpoints return errors in the browser **Network** tab or in server logs.

## Still stuck

- [GitHub Issues](https://github.com/bazoukajo/ollama-dashboard/issues) — include OS, Python version, Ollama version, and relevant log lines (redact secrets).
