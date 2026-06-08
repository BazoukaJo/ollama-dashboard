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

By default, this is expected, not a bug. The dashboard merges your saved settings into the
`options` field of requests **it sends itself** (chat, warm-load, restart, bulk-start —
`app/routes/main.py`). Ollama applies `options` strictly per-request and never stores them
against the model, so any client that talks to Ollama **directly** (VS Code's Ollama
extension, `ollama run`, `curl`, LangChain, etc.) will use Ollama's own defaults / the
model's `Modelfile` parameters instead.

> **If your client's base URL already points at `<dashboard-host>/ollama` (e.g.
> `http://localhost:5000/ollama` — check `apiBase` in `settings.json` / your extension
> config) and settings *still* aren't applied:** that route had a bug where it merged the
> *whole* stored entry (`{"settings": {...}, "source": ..., "last_updated": ...}`) into
> `options` instead of just the inner `settings` dict — so `temperature`/`top_k`/etc. never
> actually reached Ollama (`options` got `source`/`last_updated`/`settings` keys instead,
> which Ollama silently ignores). Fixed in `app/__init__.py` (`intercept_ollama_parameters`,
> ~line 176) on 2026-06-07 — **restart the dashboard** to pick up the fix; no client-side
> changes needed.

Three ways to get saved settings to external clients — see the README's
[Per-Model Settings: scope and limitations](../README.md#per-model-settings-scope-and-limitations)
for full details:

1. **Point the client at the dashboard's built-in proxy** — set its base URL /
   `apiBase` to `http://<dashboard-host>:<port>/ollama` (e.g. `http://localhost:5000/ollama`)
   instead of Ollama's `:11434` directly. No extra process, keeps original model names,
   applies every saved option exactly (`intercept_ollama_parameters` in `app/__init__.py`).
2. **Bake into Model** (Settings dialog button) — generates a `Modelfile` with `PARAMETER`
   directives for your saved values and calls Ollama's `/api/create` to build a derived model
   (named `<model>-dashboard`). Point external clients at that derived name — works even
   without the dashboard running (e.g. plain `ollama run`). A few advanced fields
   (`presence_penalty`, `frequency_penalty`, `typical_p`, `penalize_newline`) aren't valid
   Modelfile parameters and can't be baked in this way.
3. **Run `server_with_proxy.js`** (`npm install && npm run proxy`) — functionally the same
   as option 1 but as an independent Node process (default `http://localhost:11435`, no
   `/ollama` suffix); useful when the Flask dashboard isn't always running.

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

## `model_settings.json` corrupted or empty

- The file lives under the process working directory by default, or set `MODEL_SETTINGS_FILE` to an absolute path.
- Writes use a **temporary file + atomic replace**; if the file is corrupt, restore from backup or delete it to recreate defaults (per-model entries will be rebuilt as you use models).

## Logging

Set `LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, or `ERROR` (default `INFO`) before starting the app to tune console verbosity.

## Ollama version

The dashboard is tested against **recent Ollama releases**; very old servers may differ in `/api/ps` or `/api/show` shape. Upgrade Ollama if endpoints return errors in the browser **Network** tab or in server logs.

## Still stuck

- [GitHub Issues](https://github.com/bazoukajo/ollama-dashboard/issues) — include OS, Python version, Ollama version, and relevant log lines (redact secrets).
