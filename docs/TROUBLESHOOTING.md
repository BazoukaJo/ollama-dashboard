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

## My saved per-model settings aren't used by external apps / `ollama run`

By default, this is expected when clients talk to Ollama **directly** at `:11434`. The
dashboard merges saved settings into the `options` field of requests **it sends itself**
(chat, warm-load, restart, bulk-start — `app/routes/main.py`). Ollama applies `options`
strictly per-request and never stores them against the model.

### Using the dashboard API proxy (recommended)

Point the app at **`http://<dashboard-host>:<port>/ollama`** (e.g.
`http://127.0.0.1:5000/ollama`) wherever it asks for an **Ollama server address** or an
**OpenAI-compatible API base URL**. The proxy in `app/routes/proxy.py` forwards to Ollama and
merges saved settings on **inference** routes:

| Via dashboard | Settings? |
|---------------|-----------|
| `POST /ollama/v1/chat/completions` | Yes — bridged to `/api/chat` (OpenAI-compatible clients) |
| `POST /ollama/api/chat`, `/ollama/api/generate` | Yes |
| `GET /ollama/api/tags`, `GET /ollama/v1/models` | No (model listing only) |

External apps do **not** call the dashboard **Start model** API; the first chat message
loads the model. Saved `num_ctx` and other options are merged into each proxied request.

**Quick setup:**

1. Dashboard running on port 5000 (or your port).
2. Set the app's server / API base to `http://127.0.0.1:5000/ollama` — **not** raw `:11434`.
3. Use **Connect app** in the dashboard header for checks and copy-paste URLs.
4. Save per-model settings in the dashboard UI (**Settings** → **Save**).

For **dashboard MCP tools** (separate from the Ollama proxy), use **`http://127.0.0.1:5000/mcp`**
in Cursor or VS Code MCP settings. The Connect wizard lists tools and sample JSON. See
[Complete Guide — MCP tools server](GUIDE.md#mcp-tools-server-mcp).

**Examples:**

| App | Field | Value |
|-----|-------|-------|
| Ollama-compatible (generic) | Server URL | `http://127.0.0.1:5000/ollama` |
| OpenAI SDK | `base_url` | `http://127.0.0.1:5000/ollama/v1` |
| VS Code Copilot (Ollama provider) | Ollama endpoint | `http://127.0.0.1:5000/ollama` |
| Continue | `apiBase` | `http://127.0.0.1:5000/ollama` |
| Claude Code / other agents | Ollama URL | `http://127.0.0.1:5000/ollama` |

**Verify:**

```text
http://127.0.0.1:5000/ollama/v1/models
http://127.0.0.1:5000/ollama/api/tags
http://127.0.0.1:5000/ollama
```

All should return JSON. HTML 404/500 means restart the dashboard after an upgrade.

> **Historical bug (2026-06-07):** `/ollama/api/...` merged the whole stored entry instead of
> just `settings`; fixed in `app/routes/proxy.py`. Another bug double-ported `OLLAMA_HOST`
> when it carried `host:port`.

Three ways to get saved settings to external clients — see the README's
[Per-Model Settings: scope and limitations](GUIDE.md#per-model-settings-scope-and-limitations)
for full details:

1. **Point the client at the dashboard's built-in proxy** — base URL
   `http://<dashboard-host>:<port>/ollama`. Covers native `/api/...` and OpenAI-compatible
   `/v1/chat/completions`.
2. **Bake into Model** (Settings dialog button) — derived model name for clients you can't
   repoint.
3. **Run `server_with_proxy.js`** — same injection at the proxy root (port takeover on
   `:11434`). The Flask dashboard proxy at `:5000/ollama` is still recommended (CORS + `/ollama` prefix).

## Port-takeover proxy: nothing answers at `:11434`, or it won't start

This applies only if you've set up the [zero-config "port takeover" variant](GUIDE.md#per-model-settings-scope-and-limitations)
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

## IDE / external app: `exceed_context_size_error` (8192 tokens)

Symptoms: an app reports a 400 like:

```text
request (31995 tokens) exceeds the available context size (8192 tokens)
```

**Cause:** Ollama's context window for that request is **8192** (`num_ctx`), but the client
sent a much larger prompt (open files + chat history). **8192 is only the dashboard default**
— your **saved** per-model settings override it once you change and save Context in the
dashboard (or via `model_settings.json`).

If you use the dashboard proxy (`http://<host>:5000/ollama`) or port-takeover proxy
(`:11434`), saved settings — including `num_ctx` — are merged into every proxied request.
Enable **Auto-trim long prompts** in model Settings if the client sends more than the model
can hold.

**Fix:**

1. Open the model's **Settings** in the dashboard → **Context (num_ctx)** → set to what
   the model supports (e.g. **32768** or **131072**) → **Save**.
2. Restart the dashboard / Node proxy if running, then retry in the external app.
3. Alternatively, point the app at Ollama directly and set context in its own settings, or
   reduce how much workspace context it includes.

Until you save a higher `num_ctx`, the default **8192** applies — which is too small for
typical IDE prompts (~20k–100k tokens).

**Allocated context shows 4096/8192 but Settings shows more:** The **Allocated** column is
what Ollama actually loaded (`/api/ps`), not what you saved. Common causes:

1. **Model already in memory** — Ollama keeps the context size from the *first* load. Use
   **Restart model** on the dashboard card, or stop the model, then send a new message through
   `:5000/ollama`.
2. **Bypassing the proxy** — A client pointed at `:11434` directly never gets dashboard settings.
3. **Wrong base URL** — Use `http://127.0.0.1:5000/ollama` (dashboard proxy), not the raw Ollama port.

**App loads model at 4K despite saved 40K context:** Confirm the server address is
`:5000/ollama`, restart the dashboard, **restart/stop the model**, then send a new message.

**Empty or missing chat response:** Usually means the client received an empty or malformed
stream. After upgrading the dashboard, **restart** it (`restart_app.bat`), start a **new chat**,
and confirm `http://127.0.0.1:5000/ollama/v1/models` returns JSON.

**404 HTML "Not Found":** Many OpenAI-compatible clients send chat to
`POST {baseUrl}/v1/chat/completions`. The dashboard proxy must expose `/ollama/v1/...`. After
updating, restart the dashboard and confirm:

```text
http://127.0.0.1:5000/ollama/v1/models
```

returns JSON (not an HTML 404 page). Use base URL `http://127.0.0.1:5000/ollama` (no `/v1`
suffix — most clients append `/v1/chat/completions` themselves).

## VS Code Copilot: "Response too long" or bad-parameter errors

Symptoms in VS Code / Copilot Chat:

```text
Sorry, your request failed. Please try again.
Reason: Response too long.
```

or upstream 400s about unsupported parameters (`max_tokens`, `max_completion_tokens`, etc.).

**Cause:** The Copilot extension rejects very large completions client-side, and some OpenAI
fields it sends are not accepted by Ollama when clients talk to `:11434` directly.

**Fix:**

1. Point Copilot at the **dashboard proxy**, not raw Ollama:
   `http://127.0.0.1:5000/ollama` (setting:
   `github.copilot.chat.byok.ollamaEndpoint`).
2. **Restart the dashboard** after upgrades (`restart_app.bat` on Windows).
3. Start a **new Copilot chat** and retry.

The proxy (`app/services/client_payload_compat.py`) strips unsupported fields, maps
`max_completion_tokens`, caps output tokens (default **4096** via `OLLAMA_PROXY_MAX_PREDICT`),
and bridges v1 chat to native `/api/chat` so saved settings apply.

**Optional tuning:**

```bat
set OLLAMA_PROXY_MAX_PREDICT=8192
restart_app.bat
```

**Debug recent proxy requests:**

```text
http://127.0.0.1:5000/ollama/copilot-debug
```

## VS Code Copilot: reply is only the letter "I"

Symptoms:

- Copilot shows a single **`I`** (or another lone first token) instead of a full answer
- Other clients (dashboard chat, curl) get a normal response from the same model

**Cause:** VS Code Copilot sends **`reasoning_effort`** on most requests. That re-enabled
**thinking** on models like `gemma4`, which stream long internal reasoning before the real
answer. Copilot BYOK only renders **`delta.content`**, not **`delta.reasoning`**. When
thinking was mirrored into content, users often saw only the first thinking token (`I` from
"I need to…").

**Fix (dashboard proxy):**

1. **Restart the dashboard** after upgrading (`restart_app.bat`).
2. The proxy **strips `reasoning_effort`**, forces **`think: false`**, and **never sends
   `delta.reasoning`** to Copilot — only answer text in `delta.content`.
3. Start a **new Copilot chat** and retry.
4. Check **`http://127.0.0.1:5000/ollama/copilot-debug`** — recent chat entries should show
   `"native_think": false` in the pipeline metadata.

**Want the reasoning instead?** To deliberately use a thinking model's reasoning in Copilot,
open the model's **Settings** in the dashboard and set **Reasoning for external clients
(Copilot)** to **On** — the proxy then mirrors the reasoning into the visible answer (Copilot
only renders `delta.content`). **Auto** follows the client's `reasoning_effort`. The legacy
global `OLLAMA_COPILOT_ALLOW_THINKING=true` still works as an **Auto** default. Agent/tool turns
always run with thinking off regardless.

**Second cause — slow first token on big models (the most common case now that thinking is
off):** Large models that don't fit in VRAM (for example `gemma4:31b` / `qwen3.6:35b` on a
16 GB GPU) run **CPU-offloaded**. With a real Agent-mode payload (large system prompt + tool
definitions + history, ~6 k+ tokens) the **prefill alone can take ~50 s** before the first
token, and a full answer can take **2-4 minutes**. VS Code's Ollama client gives up shortly
after the first token and shows just **`I`** (whatever arrived first), even though the proxy
keeps streaming the complete answer.

**Fix (dashboard proxy):** during slow loads/prefill the proxy now sends keep-alives as
**real empty-content data chunks** (not just SSE comments) every ~5 s, so VS Code's chunk
parser counts them as activity and stays connected until the real first token. It also injects
`keep_alive` (default 15 min, `COPILOT_KEEP_ALIVE_MINUTES`) so a big model is **not reloaded**
on every turn.

**Confirm the real cause** in `data/copilot_proxy.log` — look for a `"kind": "response"` line
for the failed turn:

- `content_chars` large + `finish_reason: "stop"` → the proxy streamed the **full** answer; a
  lone `I` in VS Code is the client timing out. Tune `OLLAMA_PROXY_STREAM_HEARTBEAT_SECONDS`.
- `content_chars: 1` + `agent: true` → **the model itself returned one token then stopped**.
  This is a model-side degeneracy that oversized, CPU-offloaded reasoning models (`gemma4:31b`,
  `qwen3.6:35b` on 16 GB VRAM) hit on complex **Agent** tool-result turns. The proxy relayed
  exactly what the model produced — it is not a proxy bug.

**Workarounds for the one-token Agent degeneracy:**

1. **Use Ask mode, not Agent mode,** with these big models. Agent tool-result turns are where
   they degenerate and are slowest; in Ask mode they return full, coherent answers. Set the
   model's **Reasoning for external clients (Copilot)** to **On** to use its reasoning fully.
2. **Or use a model that fits in VRAM** for Agent mode (first token in ~1-3 s, no degeneracy):
   e.g. `qwen2.5-coder:14b`, `qwen3:14b`, `qwen3.5:9b`.

See also [GUIDE.md — VS Code Copilot](GUIDE.md#vs-code-copilot-ollama).

## VS Code Copilot: "Sorry, no response was returned"

Symptoms:

- Copilot shows **Sorry, no response was returned** with no answer text
- `copilot-debug` shows `has_tools: true` on the request

**Cause:** Copilot **Agent mode** sends **`tools`** on every request. Tool-capable models often
reply with **`tool_calls` and empty `content`**. If the proxy does not stream those tool calls
in OpenAI SSE shape (`role`, empty `content`, stringified `arguments`), Copilot treats the turn
as empty. Older proxy builds also flushed buffered thinking into `content` on tool-call turns,
which corrupted agent responses.

**Thinking models (for example `gemma4`, `qwen3.6`):** Agent turns used to leave native
**`think` unset**, so Ollama defaulted to long internal reasoning before any **`tool_calls`**.
Copilot BYOK only renders **`delta.content`**, so the chat looked empty until the client timed
out. Current proxy builds **always** force **`think: false`** on Agent/tool requests — even when
a model's **Reasoning** setting is **On** or `OLLAMA_COPILOT_ALLOW_THINKING=true` — so the tool
exchange is never corrupted by reasoning tokens.

**Fix (dashboard proxy):**

1. **Restart the dashboard** (`restart_app.bat`).
2. The proxy **forwards `tools` / `tool_choice`** to native `/api/chat` for Agent mode.
3. Use a **tool-capable model** (for example Qwen3, Llama 3.1+, or other models Ollama lists
   with tool support).
4. Check **`copilot-debug`** — agent requests should show `"agent_tools": true` in pipeline
   metadata when Copilot sent tools.

If the model returns tool calls but Copilot still shows no text, confirm the model actually
supports tools in Ollama and that VS Code Agent mode is enabled. Some models answer in plain
text even when tools are offered; others return tools only — both paths are supported by the
proxy.

## MCP: Cursor / VS Code cannot connect to `/mcp`

Symptoms:

- MCP client shows disconnected or fails to list tools
- Connect wizard **`mcp_endpoint`** check fails

**Checks:**

1. **Dashboard running** — MCP is served on the **same port** as the UI (default `:5000`), not a separate process.
2. **Correct URL** — `http://127.0.0.1:5000/mcp` (not `/ollama`, not `:11434`).
3. **Dependencies installed** — `pip install -r requirements.txt` includes `mcp` and `a2wsgi`. Restart after upgrading.
4. **Status endpoint** — `GET http://127.0.0.1:5000/api/mcp/status` should return JSON with `"ok": true`.
5. **Pair with proxy** — MCP supplies dashboard tools; chat still needs the Ollama proxy at `http://127.0.0.1:5000/ollama`.

**Ask? agent mode:** Requires a model with **tool support** (`has_tools` on the model card). The modal shows **Agent mode** when enabled. If tools never run, try a tool-capable tag (for example Qwen3) and check the server log for `/api/chat/agent` errors.

**Write tools:** `start_model` / `stop_model` are hidden unless `MCP_ALLOW_WRITE=true` and the dashboard was restarted.

See [GUIDE.md — MCP tools server](GUIDE.md#mcp-tools-server-mcp).

## VS Code Copilot: request timeout or model won't load

Symptoms:

- Copilot chat fails with a generic error or stops responding before the model answers
- Model picker shows the model but the first message never completes
- Large models (for example `gemma4:26b` with high `num_ctx`) fail on cold start while smaller models work

**VS Code has no user-configurable timeout for Ollama BYOK.** The only documented Copilot
setting for local Ollama is the endpoint URL:

```json
"github.copilot.chat.byok.ollamaEndpoint": "http://127.0.0.1:5000/ollama"
```

Open it via **File → Preferences → Settings**, search **“ollama endpoint”**, or run
**Preferences: Open User Settings (JSON)** (`Ctrl+Shift+P`). Microsoft's
[Copilot settings reference](https://code.visualstudio.com/docs/copilot/reference/copilot-settings)
does not list a timeout for Ollama BYOK or for the newer **Custom Endpoint** provider
(**Chat: Manage Language Models**). Request timeouts are built into the Copilot extension
and cannot be changed in `settings.json` today.

**Unrelated setting:** `chat.tools.terminal.enforceTimeoutFromModel` only affects **terminal
commands** in Agent mode, not LLM chat request timeouts.

**Dashboard proxy timeouts (server-side only)** — these control how long the dashboard waits
for Ollama, not how long VS Code waits on the client:

| Timeout | Seconds | Used for |
|---------|---------|----------|
| Connect | 30 | Upstream TCP connect |
| Inference (chat) | 120 | Non-streaming `/api/chat` and bridged v1 chat |
| Vision inference | 300 | Multimodal requests with images |
| Stream read | 3600 | Open SSE streams from Ollama |
| Default | 30 | Tags, show, and other short API calls |

Defined in `app/routes/proxy.py`. Raising these helps slow Ollama responses reach the proxy;
they do **not** extend VS Code's client-side wait.

**Streaming keep-alive (cold loads no longer look empty)** — Ollama withholds its HTTP response
until the model is loaded and generation starts, so a cold 20GB+ model used to send **zero
bytes** for 30-90s, which VS Code surfaces as *"Sorry, no response was returned."* The proxy now
commits the SSE response early and sends periodic **SSE comment heartbeats**
(`: ollama-dashboard keep-alive`) while the model loads or stalls, keeping the connection open
until the first token. Heartbeats are SSE comments, so OpenAI/SSE parsers ignore them — they
never appear in chat text. Tunable (server-side, restart to apply):

| Env var | Default | Meaning |
|---------|---------|---------|
| `OLLAMA_PROXY_STREAM_HEARTBEAT_SECONDS` | `10` | Idle seconds before sending a keep-alive comment (1-60) |
| `OLLAMA_PROXY_STREAM_FIRST_BYTE_GRACE_SECONDS` | `3` | How long to wait for a fast upstream error before committing the stream (0.5-30) |

**Workarounds:**

1. **Pre-start the model** in the dashboard (**Start** on the model card) before sending a
   Copilot message — avoids the cold-load wait entirely (heartbeats cover it otherwise).
2. Large models that exceed your VRAM (for example `gemma4:31b` ~20 GB or `qwen3.6:35b` ~24 GB on
   a 16 GB GPU) **are fully supported** — Ollama offloads the overflow to system RAM — they are
   just slower to load and generate. The heartbeats keep Copilot connected; for the fastest
   experience pre-start them or pick a model that fits VRAM.
3. If your client still gives up during very long loads, lower
   `OLLAMA_PROXY_STREAM_HEARTBEAT_SECONDS` (for example `5`) and restart the dashboard.
4. Check **`http://127.0.0.1:5000/ollama/proxy-debug`** or `data/copilot_proxy.log` to see
   whether VS Code disconnected before Ollama finished loading.

See also [GUIDE.md — VS Code Copilot](GUIDE.md#vs-code-copilot-ollama).

## Dashboard won't start or stop (Windows, port 5000)

| Symptom | What to do |
|---------|------------|
| `start.bat` says already running | Expected — use `stop_app.bat` or `restart_app.bat` |
| Release started but no window | Expected — release runs in the background. Check status with `scripts\dashboard-process.ps1 -Action status` or open http://127.0.0.1:5000. Logs: `data\dashboard-release-launch.log`, `data\dashboard-release-error.log` |
| Release start failed silently | Run `start.bat console` for a visible launcher, or read `data\dashboard-release-launch.log` |
| `stop_app.bat` refuses to stop | Another app (not this dashboard) owns port 5000 — check Task Manager or `netstat -aon \| findstr :5000` |
| Wrong mode after restart | Use `restart_app.bat dev` or `restart_app.bat release` to force the mode |
| Stale dev + release both running | Run `stop_app.bat` once; scripts kill all dashboard processes for this repo |

Check status:

```powershell
powershell -File scripts\dashboard-process.ps1 -Action status
```

See [GUIDE.md — Windows: start, stop, and restart](GUIDE.md#windows-start-stop-and-restart).

## `model_settings.json` corrupted or empty

- The file lives under the process working directory by default, or set `MODEL_SETTINGS_FILE` to an absolute path.
- Writes use a **temporary file + atomic replace**; if the file is corrupt, restore from backup or delete it to recreate defaults (per-model entries will be rebuilt as you use models).

## Logging

Set `LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, or `ERROR` (default `INFO`) before starting the app to tune server verbosity.

**Release mode (Windows):** Waitress runs without a console. Check `data\dashboard-release-launch.log` (startup) and `data\dashboard-release-error.log` (server output). Development mode logs to the open terminal instead.

## Ollama version

The dashboard is tested against **recent Ollama releases**; very old servers may differ in `/api/ps` or `/api/show` shape. Upgrade Ollama if endpoints return errors in the browser **Network** tab or in server logs.

## Still stuck

- [GitHub Issues](https://github.com/bazoukajo/ollama-dashboard/issues) — include OS, Python version, Ollama version, and relevant log lines (redact secrets).
