
# Copilot Instructions — ollama-dashboard

**Purpose:** Guide AI agents to be immediately productive in this codebase. Follow established patterns; do not introduce new architectural layers.

## Architecture & Data Flow
- Single Flask app (`OllamaDashboard.py`) with one blueprint (`app/routes/main.py`).
- Core logic in `OllamaService` (`app/services/ollama.py`): handles HTTP to Ollama, caching, capability detection, per-model settings, atomic JSON persistence, health reporting.
- Background thread in service updates caches (system≈2s, running≈10s, available≈30s, version≈300s). Restart process after service/capability/JS edits to clear stale caches.
- API routes: input validation → service method → standardized JSON response.

## Key Patterns & Conventions
- Always call `ollama_service.init_app(app)` after `create_app()` (see `app/__init__.py`).
- Service layer: use `_get_cached/_set_cached` for caching, never call API endpoints directly from other services/routes.
- Frontend JS (`app/static/js/main.js`): select cards via `[data-model-name]`, escape selectors with `cssEscape()`, never use index positions or raw names in inline handlers.

## Caching & Performance
- Use service getters (`get_running_models`, `get_available_models`, `get_model_info_cached`).
- Always reuse `self._session` for HTTP; never instantiate ad-hoc `requests.Session()`.
- Add new periodic data in `_background_updates_worker`; keep per-cycle additions <100ms. Expose cache age via `get_component_health()` if critical.

## Capability Flags
- Only set/extend `has_vision`, `has_tools`, `has_reasoning` in `_detect_model_capabilities` (`app/services/ollama.py`).
- Do not mutate flags in routes or JS; UI reads backend booleans passively.

## Per-Model Settings
- Stored in `model_settings.json` (atomic write: `.tmp` → `os.replace`).
- No global settings. Defaults auto-created via `_recommend_settings_for_model` (size/capability heuristics).
- All mutations guarded by `_model_settings_lock`. Never write JSON directly in routes.

## Warm Start & Service Control
- `/api/models/start/<model>`: attempts small generate (keep_alive 24h), handles transient errors with exponential backoff + optional pull + retry (max 3).
- Start/stop/restart logic in `OllamaService` only; routes wrap and return JSON.

## Persistence Files
- `history.json` (capped by `MAX_HISTORY`), `chat_history.json` (bounded 100 sessions), `model_settings.json` (per-model defaults). All use atomic write pattern.

## Model Lists & Aliases
- Curated lists in `get_best_models`/`get_all_downloadable_models` include aliases (e.g. `llava`, `moondream`) for capability tests. Preserve/extend aliases when adding models.

## Frontend Patterns
- Select cards via `[data-model-name]`; never use raw names in inline onclick. Escape dynamic HTML/selectors. Capability icons rely on backend booleans only.

## Testing & Developer Workflow
- Run all tests: `python -m pytest -q`
- Targeted test: `python -m pytest tests/test_start_model_pytest.py::test_start_model_success -q`
- Coverage: `python -m pytest --cov=app --cov-report=html`
- Playwright UI: install dev deps, then `python -m playwright install --with-deps`
- After editing service/routes/capability logic or `main.js`: restart (`Ctrl+C`, `python wsgi.py`)

## Health & Reliability
- Use `/api/health` and `get_component_health()` to inspect `background_thread_alive`, cache ages, failure counters.
- If `stale_flags.running_models` or thread dead: restart process.
- Backoff escalates to ~32s on repeated `/api/ps` failures; do not remove without replacement.

## Extension & Integration Guidelines
- New capability: extend `_detect_model_capabilities` + add UI icon logic (JS).
- New periodic data: background worker + health exposure.
- New model default heuristic: adjust `_recommend_settings_for_model` (retain normalization + locking).
- Avoid: direct Ollama HTTP in routes/JS, extra threads in request handlers, bypassing warm start logic, non-atomic JSON writes.

## Quick Commands
- Install & run: `pip install -r requirements.txt` then `python OllamaDashboard.py`
- Docker: `./scripts/build.sh`
- Example targeted test: `python -m pytest tests/test_capabilities_pytest.py::test_all_downloadable_models_include_vision_flags -q`

**Entrypoint:** Use `OllamaDashboard.py` (not `wsgi.py`).

**Feedback:** If any section is unclear or incomplete, specify which to refine.
