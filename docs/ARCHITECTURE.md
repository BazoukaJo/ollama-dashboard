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
│        Route Layer (app/routes/main.py)             │
│  - API endpoints                                    │
│  - Input validation                                 │
│  - Response serialization                           │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│        Service Layer (app/services/ollama.py)       │
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
- Background thread management (runs ~2s, ~10s, ~30s, ~300s cycles)
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

---

## Caching Strategy

| Data | TTL | Refresh Frequency | Purpose |
|------|-----|------------------|---------|
| Running models | 10s | Every ~10s in background | Keep accurate; avoid stale data |
| Available models | 30s | Every ~30s in background | Cache Ollama tags response |
| System stats | 5s | On-demand + ~2s background | Real-time performance visibility |
| Model info | 300s | On-demand | Reduce repeated /api/show calls |
| Model settings | ∞ | On write | Persistent storage in JSON |
| Version | 300s | On-demand | Ollama version rarely changes |

---

## Concurrency & Thread Safety

### Background Thread
- **Runs in daemon mode** (exits when main thread exits)
- **Updates cycle**: Sleeps 2s, checks at ~10s/~30s/~300s intervals
- **Lock-free reads**: Cache reads don't lock; stale data acceptable
- **Locked writes**: Cache writes use `_cache_lock`
- **Settings mutations**: Protected by `_model_settings_lock`

### Lock Usage
```python
with self._cache_lock:
    self._cache[key] = value
    self._cache_timestamps[key] = time.time()

with self._model_settings_lock:
    self._model_settings[model_name] = settings
    # ... write to disk ...
```

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
start_app.bat
# Uses waitress-serve on port 5000
```

**Development:**
```bash
pip install -r requirements.txt
python OllamaDashboard.py
```

**Docker (Linux, uses Gunicorn):**
```bash
docker-compose up -d
```

### Environment Configuration
```bash
export OLLAMA_HOST=localhost
export OLLAMA_PORT=11434
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
