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

## `model_settings.json` corrupted or empty

- The file lives under the process working directory by default, or set `MODEL_SETTINGS_FILE` to an absolute path.
- Writes use a **temporary file + atomic replace**; if the file is corrupt, restore from backup or delete it to recreate defaults (per-model entries will be rebuilt as you use models).

## Logging

Set `LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, or `ERROR` (default `INFO`) before starting the app to tune console verbosity.

## Ollama version

The dashboard is tested against **recent Ollama releases**; very old servers may differ in `/api/ps` or `/api/show` shape. Upgrade Ollama if endpoints return errors in the browser **Network** tab or in server logs.

## Still stuck

- [GitHub Issues](https://github.com/bazoukajo/ollama-dashboard/issues) — include OS, Python version, Ollama version, and relevant log lines (redact secrets).
