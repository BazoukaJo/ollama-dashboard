# Ollama Dashboard - Enterprise-Grade Model Monitoring

A production-ready web dashboard for monitoring, controlling, and optimizing Ollama language models. Features comprehensive observability, enterprise security, intelligent caching, and multi-tier rate limiting.

![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Status: Production Ready](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)

---

## ✨ Features

### 🎯 Core Functionality
- **Model Management**: Start, stop, restart, delete, and download Ollama models
- **Per-Model Settings**: Temperature, top-k, penalties with atomic JSON persistence
- **System Monitoring**: Real-time CPU, RAM, VRAM (GPU), and disk usage
- **Chat Interface**: Streaming inference with conversation history
- **Service Control**: Start/stop/restart Ollama service (multi-platform)
- **47 API Endpoints**: Comprehensive REST API for all operations

### 🔒 Enterprise Security
- **API Key Authentication**: Strong key-based auth with OpenSSL-grade random generation
- **Role-Based Access Control**: Three-tier roles (viewer/operator/admin)
- **Input Validation**: 20+ validation rules preventing injection attacks
- **Output Sanitization**: XSS prevention on all user-controlled content
- **CORS Restrictions**: Configurable trusted origins
- **Audit Logging**: Immutable JSON logs of all authentication/modification events
- **HTTPS Support**: TLS encryption with Let's Encrypt integration

### 📊 Observability & Monitoring
- **Prometheus Metrics**: 20+ metrics (operations, latencies, cache hits, retry rates)
- **Structured Logging**: JSON-formatted logs with trace ID propagation
- **Distributed Tracing**: OpenTelemetry-ready request tracking
- **Grafana Dashboards**: Pre-built dashboard templates
- **Health Endpoints**: Deep component health checks (/api/health, /health)
- **Performance Tracking**: Per-operation timing, success rates, anomalies
- **Alerting System**: Threshold-based alerts with webhook integration

### ⚡ Performance & Reliability
- **Smart Caching**: TTL-based in-memory cache (2s-300s intervals)
- **Rate Limiting**: Token bucket limiter (5 ops/min, 2 pulls/5min, 6 updates/min)
- **Error Handling**: 20+ transient error patterns with exponential backoff retry
- **Connection Pooling**: Persistent HTTP session with keep-alive
- **Atomic Persistence**: Atomic file writes (.tmp → os.replace()) preventing corruption
- **Graceful Shutdown**: Proper cleanup on exit via atexit hooks
- **Background Updates**: Asynchronous cache refresh (separate thread)

### 🎨 User Interface
- **Dark Mode**: Modern dark theme optimized for long sessions
- **Responsive Design**: Mobile-friendly, touch-optimized controls
- **Real-time Updates**: Auto-refresh every 30 seconds
- **Capability Icons**: Visual indicators for model capabilities (vision, tools, reasoning)
- **Compact Mode**: Space-efficient layout toggle
- **Zero Configuration**: Works out-of-the-box with sensible defaults

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Ollama running on localhost:11434
- 256MB RAM minimum

### Installation (5 minutes)

```bash
# Clone repository
git clone https://github.com/poiley/ollama-dashboard.git
cd ollama-dashboard

# Install dependencies
pip install -r requirements.txt

# Run application
python OllamaDashboard.py

# Open in browser
open http://localhost:5000
```

That's it! 🎉

### With Docker

```bash
# Build image
docker build -t ollama-dashboard .

# Run with Ollama
docker run -p 5000:5000 \
  -e OLLAMA_HOST=host.docker.internal:11434 \
  ollama-dashboard:latest
```

### With Docker Compose

```bash
# Start Ollama + Dashboard
docker-compose up -d

# Access at http://localhost:5000
```

---

## 🔐 Security Setup

### Generate API Keys

```bash
# Generate strong random keys (run for each role)
openssl rand -hex 32

# Store in .env file
cat > .env << EOF
API_KEY_VIEWER=sk-viewer-$(openssl rand -hex 32)
API_KEY_OPERATOR=sk-operator-$(openssl rand -hex 32)
API_KEY_ADMIN=sk-admin-$(openssl rand -hex 32)
EOF
```

### API Usage

```bash
# List models (viewer access)
curl -H "Authorization: Bearer sk-viewer-..." \
  http://localhost:5000/api/models/running

# Start model (operator access)
curl -X POST -H "Authorization: Bearer sk-operator-..." \
  http://localhost:5000/api/models/start/llama3.1:8b

# Delete model (admin access)
curl -X DELETE -H "Authorization: Bearer sk-admin-..." \
  http://localhost:5000/api/models/delete/old-model
```

---

## 📚 Documentation

- **[Architecture Guide](docs/ARCHITECTURE.md)** — Service composition, data flow, caching strategy
- **[Deployment Guide](docs/DEPLOYMENT.md)** — Docker, Gunicorn, Kubernetes, Helm
- **[Security Guide](docs/SECURITY.md)** — Auth, CORS, validation, compliance
- **[API Reference](#api-endpoints)** — All 47 endpoints documented below

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────┐
│         Ollama Dashboard (You)            │
├──────────────────────────────────────────┤
│ Flask Web Framework (HTTP routing)        │
│ + CORS, Security Headers, Auth Middleware│
├──────────────────────────────────────────┤
│ Route Layer (47 API endpoints)            │
│ + Input validation, Serialization        │
├──────────────────────────────────────────┤
│ OllamaService (Main Orchestrator)        │
│ ├─ OllamaServiceCore (caching, bg)      │
│ ├─ OllamaServiceModels (operations)     │
│ ├─ OllamaServiceControl (service mgmt)  │
│ ├─ OllamaServiceUtilities (settings)    │
│ ├─ TransientErrorDetector                │
│ ├─ PerformanceMetrics                    │
│ ├─ RateLimiter (3 operation types)      │
│ └─ ... (PrometheusMetrics, Tracing)     │
├──────────────────────────────────────────┤
│ HTTP Client (requests.Session)            │
│ + Connection pooling, Keep-alive         │
├──────────────────────────────────────────┤
│ Ollama API (localhost:11434)              │
│ /api/ps, /api/tags, /api/generate, etc.  │
└──────────────────────────────────────────┘
```

---

## 📊 API Endpoints (47 Total)

### Model Management (11)
```
GET  /api/models/running              — List running models
GET  /api/models/available            — List available models
GET  /api/models/downloadable         — List curated models
POST /api/models/start/<model>        — Start a model
POST /api/models/stop/<model>         — Stop a model
POST /api/models/restart/<model>      — Restart a model
DELETE /api/models/delete/<model>     — Delete a model
POST /api/models/pull/<model>         — Download a model
GET  /api/models/info/<model>         — Get model details
GET  /api/models/status/<model>       — Get model status
POST /api/models/bulk/start           — Start multiple models
```

### Model Settings (7)
```
GET    /api/models/settings/<model>         — Get settings
GET    /api/models/settings/recommended/<m> — Get recommended
POST   /api/models/settings/<model>         — Save settings
DELETE /api/models/settings/<model>         — Delete settings
POST   /api/models/settings/<model>/reset   — Reset to default
POST   /api/models/settings/apply_all_recommended  — Batch apply
POST   /api/models/settings/migrate         — Legacy migration
```

### Chat (4)
```
POST /api/chat                    — Send prompt (streaming)
GET  /api/chat/history            — Get conversation history
POST /api/chat/history            — Save session
GET  /api/models/performance/<m>  — Get model perf stats
```

### System Monitoring (6)
```
GET /api/system/stats              — CPU, RAM, VRAM, disk
GET /api/system/stats/history      — Historical stats
GET /api/models/memory/usage       — Per-model memory
GET /api/metrics/performance       — Op timing stats
GET /metrics                       — Prometheus metrics
GET /health                        — Health check (k8s)
```

### Service Control (5)
```
GET  /api/service/status           — Check Ollama running
POST /api/service/start            — Start Ollama service
POST /api/service/stop             — Stop Ollama service
POST /api/service/restart          — Restart Ollama service
POST /api/full/restart             — Full app restart
```

### Observability (4)
```
GET /api/health                    — Component health
GET /api/metrics/rate-limits       — Rate limit status
GET /api/metrics/summary           — Metrics summary
GET /api/observability/alerts      — Current alerts
```

### Utilities & Admin (10+)
```
GET  /                             — Main dashboard
GET  /api/version                  — Ollama version
GET  /admin/model-defaults         — Admin settings page
POST /api/reload_app               — Reload application
POST /api/force_kill               — Force kill process
GET  /api/test                     — API test endpoint
GET  /api/test-models-debug        — Debug endpoint
... (more endpoints)
```

---

## ⚙️ Configuration

All configuration via environment variables:

```bash
# Ollama connection
OLLAMA_HOST=localhost              # Ollama hostname
OLLAMA_PORT=11434                  # Ollama port

# API Keys (generate with: openssl rand -hex 32)
API_KEY_VIEWER=sk-viewer-...       # Read-only access
API_KEY_OPERATOR=sk-operator-...   # Start/stop models
API_KEY_ADMIN=sk-admin-...         # Full access

# Persistence
HISTORY_FILE=history.json          # Chat history
MODEL_SETTINGS_FILE=model_settings.json
MAX_HISTORY=50                     # Max history entries

# Security & CORS
CORS_ORIGINS=http://localhost:5000 # Comma-separated trusted origins
HTTPS_ENABLED=false                # HTTPS support

# Logging
LOG_LEVEL=INFO                     # Logging level
AUDIT_LOG_FILE=logs/audit.log      # Audit trail

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=       # OpenTelemetry collector (optional)
ALERT_WEBHOOK_URL=                 # Webhook for alerts (optional)
```

Create `.env` file with your settings; defaults are sensible for single-user.

---

## 📈 Performance

### Metrics
- **Startup**: <5 seconds
- **First request**: <1 second (cold)
- **Subsequent requests**: <100ms (warm)
- **Concurrent users**: 10-50 (single instance)
- **Memory footprint**: ~100MB base + 50MB per 100 models

### Scalability

| Users | Setup | Notes |
|-------|-------|-------|
| 1-10 | Single Flask process | Out-of-box default |
| 10-50 | Gunicorn + Nginx | 4-8 workers |
| 50-500 | Kubernetes + Redis | Distributed caching |
| 500+ | Full enterprise | Multiple instances, DB backend |

See [Deployment Guide](docs/DEPLOYMENT.md) for scaling instructions.

---

## 🔄 Background Updates

The service runs periodic background updates (separate thread):

| Data | Interval | TTL |
|------|----------|-----|
| Running models | ~10s | 10s |
| Available models | ~30s | 30s |
| System stats | ~2s | 5s |
| Ollama version | ~300s | 300s |

The background thread is automatically managed; restarts on crash.

---

## 🛠️ Development

### Testing

```bash
# Run all tests
python -m pytest -q

# Run specific test
python -m pytest tests/test_start_model_pytest.py::test_start_model_success -q

# Coverage report
python -m pytest --cov=app --cov-report=html
open htmlcov/index.html

# Visual layout tests (no browser; catches HTML/CSS regressions)
python -m pytest tests/test_visual_layout.py -v

# UI testing (Playwright; requires: pip install pytest-playwright && playwright install)
python -m pytest tests/test_ui_playwright.py -q
```

### Code Quality

```bash
# Linting
pylint app/

# Type checking
mypy app/

# Code formatting
black app/
isort app/

# Security scanning
bandit -r app/
pip audit
```

### Workflow

```bash
# After editing service/routes/UI:
1. git add .
2. python -m pytest -q           # Run tests
3. Restart: Ctrl+C, python OllamaDashboard.py
4. Test in browser: http://localhost:5000
```

---

## 🐛 Troubleshooting

### Models show as "running" but shouldn't
- Background cache is stale; wait 10-15 seconds
- Restart app: `Ctrl+C`, then `python OllamaDashboard.py`

### Settings changes not persisting
- Check permissions: `ls -la model_settings.json`
- Ensure app directory is writable: `chmod 755 app/`

### High memory usage
- Reduce cache size in `OllamaServiceCore`
- Switch to Redis backend for distributed caching

### Slow response times
- Check Ollama status: `curl http://localhost:11434/api/ps`
- Monitor system resources: `top`, `free -h`

See [Architecture Guide](docs/ARCHITECTURE.md) for more troubleshooting.

---

## 📦 Dependencies

Minimal dependencies for maximum compatibility:

```
Flask==3.0.0           # Web framework
requests==2.31.0       # HTTP client
psutil==5.9.6          # System stats
pytz==2023.3           # Timezone support
prometheus-client      # Metrics export
flask-cors==4.0.0      # CORS support
```

Optional (for advanced features):
```
redis                  # Distributed caching
sqlalchemy             # Database ORM
gunicorn               # Production server
```

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-thing`
3. Add tests for new functionality
4. Ensure tests pass: `pytest -q`
5. Submit pull request

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/poiley/ollama-dashboard/issues)
- **Documentation**: [docs/](docs/)
- **Community**: [Ollama Discord](https://discord.gg/ollama)

---

## 🗺️ Roadmap

- [x] Model management (CRUD)
- [x] System monitoring (CPU, RAM, VRAM, disk)
- [x] Chat interface with history
- [x] Per-model settings persistence
- [x] Enterprise security (auth, RBAC, audit logging)
- [x] Comprehensive observability (metrics, logging, tracing)
- [x] Kubernetes deployment ready
- [ ] Async/FastAPI migration (Phase 3)
- [ ] Multi-Ollama instance support
- [ ] Model versioning & rollback
- [ ] Scheduled model operations
- [ ] Multi-tenant isolation
- [ ] Advanced RBAC (fine-grained permissions)
- [ ] SAML/OAuth authentication

---

## 🎉 Acknowledgments

Built with ❤️ for the Ollama community.

Inspired by:
- [Ollama](https://ollama.ai/) - The amazing LLM framework
- [Flask](https://flask.palletsprojects.com/) - Lightweight web framework
- [Prometheus](https://prometheus.io/) - Metrics and alerting
- Best practices from enterprise Python applications

---

**Made with** ☕ **and** 🚀 **for Ollama enthusiasts everywhere.**
