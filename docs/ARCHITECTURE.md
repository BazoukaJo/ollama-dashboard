# Ollama Dashboard Architecture Guide

## Overview

Ollama Dashboard is a Flask-based web interface for monitoring and controlling Ollama models. It's designed with clean separation of concerns, comprehensive observability, and enterprise-grade security.

### Design Principles
- **Single Responsibility**: Each service has one clear purpose
- **Dependency Injection**: Services receive dependencies; no global state
- **Fail-Safe**: Graceful degradation when Ollama is unavailable
- **Observable**: Full request tracing, metrics, and audit logging
- **Secure by Default**: Authentication, authorization, input validation

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│            Browser / HTTP Client                    │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│        Flask Web Framework (OllamaDashboard.py)     │
│  - HTTP routing & request/response handling         │
│  - Middleware (CORS, security headers, etc.)        │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│        Route Layer (app/routes/main.py)             │
│  - 47 API endpoints                                 │
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
│  │ Enterprise Improvements                        │ │
│  │  • TransientErrorDetector                      │ │
│  │  • PerformanceMetrics                          │ │
│  │  • RateLimiter (3 operation types)            │ │
│  │  • PrometheusMetrics (observability)          │ │
│  │  • DistributedTracing (request tracking)      │ │
│  │  • StructuredLogging (JSON logs)              │ │
│  │  • AlertManager (threshold-based alerts)      │ │
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
    """Combines all functionality with enterprise improvements."""
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

#### Enterprise Improvements
- `TransientErrorDetector`: Classifies errors (20+ patterns)
- `PerformanceMetrics`: Tracks operation timing, anomalies
- `RateLimiter`: Token bucket (5 ops/min, 2 pulls/5min)
- `PrometheusMetrics`: Full observability
- `DistributedTracing`: Request ID propagation
- `StructuredLogging`: JSON logs with context
- `AlertManager`: Severity-based alerting

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
service: ollama_service.start_model(model_name)
    ├─ Check rate limit (model_operations: 5/min)
    ├─ Check if already running (get_running_models)
    ├─ If running: return {"success": true, "message": "already running"}
    ├─ If not running:
    │  ├─ POST /api/generate with small prompt (keep_alive=24h)
    │  ├─ Retry up to 3x with exponential backoff if transient error
    │  ├─ Record performance metrics (duration, success)
    │  └─ Refresh running models cache
    └─ Return JSON response

Response: 200 OK
{
    "success": true,
    "message": "Model llama3.1:8b started successfully",
    "duration_seconds": 8.3
}
```

### Example 2: Get System Stats
```
GET /api/system/stats
    ↓
route handler: system_stats()
    ↓
validation: (GET request, no input)
    ↓
service: ollama_service.get_system_stats()
    ├─ Check cache (ttl_seconds=5)
    ├─ If cached & fresh: return cached data
    ├─ If stale or missing:
    │  ├─ Collect system stats (CPU, RAM, disk)
    │  ├─ Get GPU VRAM (nvidia-ml-py, GPUtil, nvidia-smi fallback)
    │  ├─ Cache result
    │  └─ Record performance metric
    └─ Return JSON response

Response: 200 OK
{
    "success": true,
    "stats": {
        "cpu": {"percent": 24.5},
        "memory": {"percent": 35.2, ...},
        "vram": {"total": 8000, "used": 3200, ...},
        "disk": {"percent": 42.1, ...}
    }
}
```

### Example 3: Save Model Settings
```
POST /api/models/settings/llama3.1:8b
    ↓
request body:
{
    "temperature": 0.8,
    "top_k": 50,
    "num_predict": 512
}
    ↓
validation: numeric ranges (temperature 0-2, top_k 1-100, etc.)
    ↓
service: ollama_service.save_model_settings(model_name, settings)
    ├─ Acquire _model_settings_lock (thread-safe)
    ├─ Load current settings from model_settings.json
    ├─ Merge new settings (user overrides defaults)
    ├─ Validate merged settings (types, bounds)
    ├─ Atomic write: write to .tmp, os.replace() to .json
    ├─ Release lock
    └─ Return success

Response: 200 OK
{
    "success": true,
    "message": "Settings saved for llama3.1:8b"
}
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

### Cache Operations

```python
# Get from cache (with TTL check)
value = self._get_cached('running_models', ttl_seconds=10)
if value is not None:
    return value

# If not in cache or stale, fetch fresh
response = self._session.get(f'{self.ollama_host}/api/ps')
data = response.json().get('models', [])

# Store in cache
self._set_cached('running_models', data)
return data
```

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
# Thread-safe cache write
with self._cache_lock:
    self._cache[key] = value
    self._cache_timestamps[key] = time.time()

# Thread-safe settings access
with self._model_settings_lock:
    self._model_settings[model_name] = settings
    # ... write to disk ...
```

### Rate Limiting
```python
# Token bucket: 5 requests per 60 seconds
limiter = RateLimiter(max_requests=5, window_seconds=60)

if not limiter.allow_request():
    return {"error": "Rate limit exceeded"}, 429

# If allowed, request proceeds
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
        # All retries exhausted
        return error_response
```

### Permanent Errors (Fail Fast)
**Patterns**: Not found, invalid, unauthorized, forbidden, no such file

```python
try:
    response = self._session.post(...)
    if "model not found" in response.text.lower():
        return {"error": "Model does not exist", "success": false}
except PermanentError:
    return error_response  # No retry
```

---

## Health & Monitoring

### Component Health Checks
```python
health = ollama_service.get_component_health()
# Returns:
{
    "background_thread_alive": true,
    "cache_ages": {
        "running_models": 2.5,     # seconds old
        "available_models": 8.1
    },
    "failure_counters": {
        "consecutive_ps_failures": 0
    },
    "retry_metrics": {
        "total_attempts": 142,
        "successful": 138,
        "failed": 4
    }
}
```

### Prometheus Metrics
Exported at `/metrics` endpoint:
- `ollama_active_models` (gauge)
- `ollama_available_models` (gauge)
- `ollama_model_operations_total` (counter)
- `ollama_retry_attempts_total` (counter)
- `ollama_request_duration_seconds` (histogram)
- ... (15+ metrics total)

---

## Security Architecture

### Authentication
- API key required for all `/api/*` endpoints
- Roles: `viewer` (read-only), `operator` (write), `admin` (delete/control)
- Keys stored in environment variables

### Input Validation
- Model names: Alphanumeric + hyphens/underscores/colons (Ollama standard)
- Numeric ranges: Min/max bounds enforced
- JSON payloads: Schema validation

### Output Sanitization
- All model names HTML-escaped before rendering
- JSON responses safe (no raw HTML)
- Security headers on all responses

### Audit Logging
- All authentication events logged to `logs/audit.log`
- Model operations logged (start, stop, delete)
- Settings changes logged

---

## Scalability Considerations

### Single Instance (Current)
- ✅ In-memory caching
- ✅ Local JSON persistence
- ✅ Single Flask process
- ⚠️ ~10-50 concurrent users max

### Multi-Worker (Gunicorn)
- ✅ 4-8 Flask workers behind Nginx
- ⚠️ Separate cache per worker (not shared)
- ⚠️ JSON lock contention on settings writes
- ✅ ~50-200 concurrent users

### Distributed (Multiple Instances)
- 🔄 Shared Redis cache
- 🔄 Shared database for settings (MongoDB or PostgreSQL)
- 🔄 Load balancer (Nginx, HAProxy)
- ✅ 200+ concurrent users

---

## Quick Reference

### Starting the App
```bash
pip install -r requirements.txt
python OllamaDashboard.py
```

### Environment Configuration
```bash
export OLLAMA_HOST=localhost
export OLLAMA_PORT=11434
export API_KEY_VIEWER=sk-viewer-...
export API_KEY_OPERATOR=sk-operator-...
export API_KEY_ADMIN=sk-admin-...
python OllamaDashboard.py
```

### Checking Health
```bash
curl http://localhost:5000/api/health
```

### Prometheus Metrics
```bash
curl http://localhost:5000/metrics
```

---

## Troubleshooting

**Q: Models show as "running" but Ollama API returns 0 models**
A: Background thread cache is stale. Wait 10-15 seconds or restart the app.

**Q: Settings changes not persisting**
A: Check `model_settings.json` file permissions. Ensure app has write access to `app/` directory.

**Q: High memory usage with many models**
A: Background thread caches full model info. Reduce cache size or increase TTL in `app/services/ollama_core.py`.

**Q: Rate limit errors even with low traffic**
A: Multiple workers (Gunicorn) each have independent rate limiters. Use Redis backend for shared limits.

---

## Architecture Decision Records (ADRs)

### ADR-001: Mixin Composition over Inheritance
**Decision**: Use multiple inheritance (mixins) instead of deep inheritance chain.
**Rationale**: Flexibility, cleaner separation of concerns, easier testing.
**Trade-off**: MRO complexity, requires type checking blocks.

### ADR-002: In-Memory Cache over Database
**Decision**: Use Python dict with TTL instead of external database.
**Rationale**: Simplicity, no additional dependencies, sufficient for <50 users.
**Trade-off**: Not distributed; lost on restart; not suitable for horizontal scaling.

### ADR-003: Atomic File Writes for Settings
**Decision**: Write to `.tmp` file then `os.replace()` instead of direct write.
**Rationale**: Prevent corruption if process crashes mid-write.
**Trade-off**: Slightly slower; requires filesystem that supports atomic rename.

### ADR-004: Flask over FastAPI (Initially)
**Decision**: Use Flask for simplicity, plan FastAPI migration later.
**Rationale**: Lower complexity for Phase 1; easier to port existing code.
**Trade-off**: Synchronous I/O; threads for concurrency; no automatic API docs.

---

## References

- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Prometheus Metrics Documentation](https://prometheus.io/docs/concepts/data_model/)
