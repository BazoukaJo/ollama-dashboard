# AI Coding Agent Instructions for `ollama-dashboard`

## 1. Architecture Overview
Flask app with factory (`app/__init__.py`) + single blueprint (`app/routes`). Core logic lives in `OllamaService` (`app/services/ollama.py`) which handles Ollama API calls, caching, background data collection, and capability detection. Routes are thin controllers delegating to the service. Templates + static assets under `app/templates` and `app/static`.

## 2. Data & Background Flow
`OllamaService` starts a background thread (`_background_updates_worker`) that periodically refreshes: system stats (≈2s), running models (≈10s), available models + version (≈30s / 5m). Results cached in `self._cache` with TTL access via `_get_cached`. Prefer using service getters rather than new direct HTTP calls to avoid duplicating logic.

## 3. Core Service Patterns
- All outgoing Ollama requests use the session (`self._session`) for reuse.
- Use `get_running_models()` for normalized model entries: includes formatted sizes, families string, capability flags, expiration formatting.
- Capability detection central in `_detect_model_capabilities`: vision inferred by name (`llava`, `bakllava`, `moondream`, `qwen*-vl`, etc.) or families containing `clip` / `projector`.
- Downloadable model lists: `get_best_models()`, `get_all_downloadable_models()`, `get_downloadable_models(category)` with `category` = `best|all`.

## 4. Routes & Response Conventions
- Routes live in `app/routes/main.py` on blueprint `bp` imported from `app/routes/__init__.py`.
- Error normalization for model operations via `_handle_model_error` returning `{success: False, message: ...}` + HTTP code.
- Success responses for pull/start/delete maintain `{success: bool, message: str}` pattern.
- Some helpers (`_json_success`, `_json_error`) unify JSON structure—reuse them when adding similar endpoints.
- Health endpoints: `/ping` (factory) + `/api/health` (aggregated status with uptime + system metrics).

## 5. Warm Start & Model Management
`/api/models/start/<model>` attempts a generate first; on failure attempts a pull then generates again. Keep this retry flow intact; extend by adjusting error classification only inside `_handle_model_error`.
Stopping models prefers graceful unload (generate with `keep_alive: 0s`) before scanning/killing processes (Windows + *nix fallbacks). Do NOT bypass this without justification.

## 6. System & Capability Surfaces
System stats: `get_system_stats()` pulls cached values; VRAM via multiple strategies (pynvml, GPUtil, `nvidia-smi`). If adding metrics, modify `_get_system_stats_raw` and ensure thread still lightweight (<100ms typical).
Model capabilities currently limited to vision; tools/reasoning placeholders retained for future expansion—set them explicitly if implementing.

## 7. Configuration & Environment
Runtime config via env vars consumed in `Config` or app factory: `OLLAMA_HOST`, `OLLAMA_PORT`, `MAX_HISTORY`, `HISTORY_FILE`, `SETTINGS_FILE`. Docker uses these defaults; do not hardcode host/port in new code—always read from `app.config` or env fallback inside service when `self.app` absent.
Settings persistence: JSON file (`settings.json`) accessed via `load_settings()` / `save_settings()`; type coercion + defaults applied. Extend settings by adding to `get_default_settings()` and validation loop in `save_settings()`.

## 8. History & State
Running model snapshots stored in memory + persisted to `history.json` via `update_history()` / `save_history()`. Chat history stored separately in `chat_history.json` via `get_chat_history()` / `save_chat_session()`. When introducing new persisted artifacts, follow this pattern: atomic write (open, dump), capped length, ISO timestamps. Both files live in workspace root by default; Docker mounts `history.json` as volume.

## 9. Testing Patterns
Test suite uses both `unittest` (`tests/test_ollama_service.py`) and `pytest` (e.g. `tests/test_start_model_pytest.py`). Common mocking strategy: patch network calls (`@patch('app.routes.main.requests.post')`) or service methods. New tests should prefer pytest style for clarity unless extending existing unittest file. Quick run: `python -m pytest -q`. For targeted capability tests see `tests/test_capabilities_pytest.py`.

## 10. Adding New Functionality
- Put external/Ollama interaction in `OllamaService` (keep routes thin).
- Cache results if called frequently; pick TTL matching volatility (e.g. metadata 300s, live stats ≤10s).
- Reuse error patterns: return structured JSON + appropriate status; avoid raising raw exceptions in routes.
- When adding a route needing model info, use `get_model_info_cached(model_name)` before a costly API call.

## 11. Performance & Safety Guidelines
- Avoid blocking operations in request path—push periodic tasks into background thread when feasible.
- Respect existing retry / timeout values (e.g. generate: timeout ~30–120s; pull: large timeout 3600s).
- Do not spawn additional long-lived threads without consolidating into `_background_updates_worker`.

## 12. Frontend Integration Notes
Capability icons rendered in `app/static/js/main.js`; if adding new capability flags, ensure service sets explicit boolean fields and update JS/icon mapping together.

## 13. Common Pitfalls
- Directly re-calling Ollama endpoints without session can degrade performance—use `self._session`.
- Forgetting to initialize service with app (`ollama_service.init_app(app)`) leads to missing config/history; factory handles this via `init_main_bp(app)`.
- Modifying time formatting: keep local + relative dual representation used in running models.

## 14. Deployment & Scripts
Entry point: `wsgi.py` (runs on port 5000). Windows monitoring & service control scripts in `scripts/`. Docker config in `docker/` (compose + gunicorn). Keep new operational scripts in `scripts/` with concise README updates.

Docker-specific: Ollama accessed via `host.docker.internal` (set in `OLLAMA_HOST`). When debugging startup failures, check: 1) Ollama service status, 2) Port 5000 availability, 3) Python process cleanup (`Stop-Process -Name python -Force`), 4) Background thread initialization in `OllamaService.init_app()`.

## 15. Debugging & Common Issues
**App won't start**: Most failures traced to: (a) Ollama service not running, (b) Port 5000 already bound, (c) Orphaned Python processes. Solution: Clean processes (`Stop-Process -Name python -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2`), verify Ollama status, then start.

**Service initialization errors**: If `ollama_service` methods fail, ensure `init_app()` called in blueprint init (`app/routes/__init__.py` calls `init_main_bp(app)`). Service requires app context for config/history access.

**Test failures**: Mock pattern: `@patch('app.routes.main.requests.post')` + `@patch('app.routes.main.ollama_service.get_running_models')`. Always mock both network + service methods to avoid real API calls. See `tests/test_start_model_pytest.py` for canonical pattern.

## 16. Extension Strategy Example
Example: Add per-model token throughput stats:
1. Extend `get_model_performance()` to record timestamped metrics.
2. Append to a capped JSON file `model_perf_history.json` (≤100 entries/model).
3. New route `/api/models/performance/<model>/history` delegating to service method.

---
Provide feedback if additional conventions or workflows seem unclear so this doc can be refined.
