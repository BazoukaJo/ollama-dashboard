#!/bin/bash
# Quick Reference: Ollama Dashboard 10/10 Plan Execution

# ============================================================================
# QUICK START - Phase 1 Verification
# ============================================================================

# Test that app starts
python OllamaDashboard.py &
sleep 2
curl http://localhost:5000/api/health
pkill -f OllamaDashboard.py

# Run all tests
python -m pytest -q

# ============================================================================
# Phase 2: Security (Week 2.5-3.5) - Next Steps
# ============================================================================

# 1. Review auth implementation
# File: app/services/auth.py (336 lines)
# Includes: API keys, RBAC, audit logging, decorators

# 2. Review validators
# File: app/services/validators.py (248 lines)
# Includes: Input validation, output sanitization

# 3. Wire into routes (main.py)
# TODO: Add @require_auth decorator to all /api/* routes
# TODO: Add input validation to route parameters

# 4. Test auth
curl -H "Authorization: Bearer sk-admin-..." \
  http://localhost:5000/api/models/running

# ============================================================================
# Phase 3: Async/FastAPI (Week 4-5.5)
# ============================================================================

# 1. Create FastAPI parallel app
# mkdir app_async/
# Create async route handlers
# Convert services to async-compatible

# 2. Load test
# pip install locust
# locust -f tests/load_test.py

# ============================================================================
# Phase 4: Observability (Week 6)
# ============================================================================

# 1. Wire Prometheus metrics
# curl http://localhost:5000/metrics

# 2. Set up Grafana
# docker run -d -p 3000:3000 grafana/grafana
# Import dashboard: dashboards/ollama-dashboard.json

# 3. Test tracing
# grep "trace_id" logs/audit.log

# ============================================================================
# Phase 5: Documentation & Kubernetes (Week 6.5-7)
# ============================================================================

# 1. Kubernetes deployment
# kubectl apply -f k8s/
# kubectl get pods -n ollama-dashboard

# 2. Helm deployment
# helm install ollama-dashboard ./helm

# 3. API documentation
# FastAPI /docs and /redoc auto-generate

# ============================================================================
# Phase 5.5: Polish (Week 7.5)
# ============================================================================

# Check code quality
mypy app/
pylint app/
black --check app/
pip audit

# Check test coverage
pytest --cov=app --cov-report=html
open htmlcov/index.html

# ============================================================================
# DOCKER COMMANDS
# ============================================================================

# Build
docker build -t ollama-dashboard .

# Run
docker run -p 5000:5000 \
  -e OLLAMA_HOST=localhost:11434 \
  -e API_KEY_ADMIN=sk-admin-... \
  ollama-dashboard

# Docker Compose
docker-compose up -d
docker-compose logs -f dashboard

# ============================================================================
# KUBERNETES COMMANDS
# ============================================================================

# Create namespace
kubectl create namespace ollama-dashboard

# Deploy
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Check status
kubectl get pods -n ollama-dashboard
kubectl logs -f deployment/ollama-dashboard -n ollama-dashboard

# Port forward
kubectl port-forward svc/ollama-dashboard 5000:80 -n ollama-dashboard

# ============================================================================
# API TESTING COMMANDS
# ============================================================================

# Set API key
API_KEY="sk-admin-changeme"

# Get health
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/health

# Get running models
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/models/running

# Start model
curl -X POST -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/models/start/llama3.1:8b

# Stop model
curl -X POST -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/models/stop/llama3.1:8b

# Delete model
curl -X DELETE -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/models/delete/old-model

# Get system stats
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/system/stats

# Get Prometheus metrics
curl http://localhost:5000/metrics

# ============================================================================
# DOCUMENTATION FILES
# ============================================================================

# Architecture (700 lines)
open docs/ARCHITECTURE.md

# Deployment (650 lines)
open docs/DEPLOYMENT.md

# Security (500 lines)
open docs/SECURITY.md

# Implementation Status
open IMPLEMENTATION_STATUS.md

# Phase 1 Complete
open PHASE1_COMPLETE.md

# Master Plan
open MASTER_PLAN.md

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

# Create .env file
cat > .env << EOF
# Ollama connection
OLLAMA_HOST=localhost
OLLAMA_PORT=11434

# API Keys (generate with: openssl rand -hex 32)
API_KEY_VIEWER=sk-viewer-$(openssl rand -hex 32)
API_KEY_OPERATOR=sk-operator-$(openssl rand -hex 32)
API_KEY_ADMIN=sk-admin-$(openssl rand -hex 32)

# Persistence
HISTORY_FILE=history.json
MODEL_SETTINGS_FILE=model_settings.json
MAX_HISTORY=50

# Logging
LOG_LEVEL=INFO
AUDIT_LOG_FILE=logs/audit.log

# Security
CORS_ORIGINS=http://localhost:5000,http://127.0.0.1:5000
HTTPS_ENABLED=false

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=
ALERT_WEBHOOK_URL=
EOF

# Load environment
source .env

# ============================================================================
# TESTING COMMANDS
# ============================================================================

# Run all tests
pytest -q

# Run specific test file
pytest tests/test_start_model_pytest.py -q

# Run specific test
pytest tests/test_start_model_pytest.py::test_start_model_success -q

# Coverage report
pytest --cov=app --cov-report=html
pytest --cov=app --cov-report=term

# With verbose output
pytest -v --tb=short

# ============================================================================
# USEFUL TOOLS
# ============================================================================

# API key generation
openssl rand -hex 32

# Check if port is in use
lsof -i :5000

# Kill process on port
pkill -f OllamaDashboard.py

# Monitor logs
tail -f logs/audit.log
tail -f logs/app.log

# Check Ollama status
curl http://localhost:11434/api/ps
curl http://localhost:11434/api/tags
curl http://localhost:11434/api/version

# ============================================================================
# PHASE COMPLETION CHECKLIST
# ============================================================================

# Phase 1: Architecture ✅
# [ ] Service composition fixed
# [ ] All 47 endpoints functional
# [ ] Architecture docs complete
# [ ] Tests passing

# Phase 2: Security (NEXT)
# [ ] Auth middleware integrated
# [ ] RBAC enforced
# [ ] Input validation active
# [ ] Audit logging working
# [ ] All tests passing

# Phase 3: Async/FastAPI
# [ ] FastAPI parallel app created
# [ ] Routes converted to async
# [ ] Load test passed (100 users)
# [ ] Flask replaced with FastAPI

# Phase 4: Observability
# [ ] Structured logging active
# [ ] Request tracing working
# [ ] Prometheus metrics exported
# [ ] Grafana dashboards created

# Phase 5: Documentation
# [ ] API docs (OpenAPI) complete
# [ ] Kubernetes manifests working
# [ ] Helm chart functional
# [ ] All guides updated

# Phase 5.5: Polish
# [ ] >85% test coverage
# [ ] Type checking passes
# [ ] Linting clean
# [ ] Security baseline met

# ============================================================================
# QUICK REFERENCE: FILE STRUCTURE
# ============================================================================

# Service Layer
app/services/
  ├── ollama.py                  # Main service (180 lines)
  ├── contracts.py               # ABCs (97 lines) NEW
  ├── auth.py                    # Authentication (336 lines) NEW
  ├── validators.py              # Validation/sanitization (248 lines) NEW
  ├── ollama_core.py             # Caching, background (496 lines)
  ├── ollama_models.py           # Model ops (297 lines)
  ├── ollama_service_control.py  # Service mgmt (639 lines)
  ├── ollama_utilities.py        # Settings, history (537 lines)
  └── ... (10+ other services)

# Routes
app/routes/
  ├── main.py                    # 47 API endpoints (1333 lines)
  ├── monitoring.py              # Metrics endpoints
  └── observability.py           # Health/alerts endpoints

# Documentation
docs/
  ├── ARCHITECTURE.md            # 700 lines NEW
  ├── DEPLOYMENT.md              # 650 lines NEW
  └── SECURITY.md                # 500 lines NEW

# Management Docs
├── README.md                    # 400+ lines (updated)
├── MASTER_PLAN.md               # This plan
├── IMPLEMENTATION_STATUS.md     # Phase checklist
└── PHASE1_COMPLETE.md          # Phase 1 summary

# Configuration
├── .env                         # Environment variables (create)
├── config/.env.example          # Example config
├── requirements.txt             # Python dependencies
├── docker-compose.yml           # Local dev environment
├── Dockerfile                   # Container image
├── gunicorn_config.py           # Production server
└── nginx.conf                   # Web server (example)

# Kubernetes
k8s/
  ├── namespace.yaml
  ├── configmap.yaml
  ├── secret.yaml
  ├── deployment.yaml
  ├── service.yaml
  ├── hpa.yaml                   # Autoscaling
  └── ingress.yaml

# Helm
helm/
  ├── Chart.yaml
  ├── values.yaml
  ├── values-prod.yaml
  └── templates/
      ├── deployment.yaml
      ├── service.yaml
      └── ... (other K8s objects)

# ============================================================================
# MILESTONE DATES
# ============================================================================

# Week 1-2:   Phase 1 ✅ (Jan 15)
# Week 2.5-3.5: Phase 2 ⏳ (Jan 25 target)
# Week 4-5.5: Phase 3 ⏳ (Feb 8 target)
# Week 6:     Phase 4 ⏳ (Feb 15 target)
# Week 6.5-7: Phase 5 ⏳ (Feb 22 target)
# Week 7.5:   Phase 5.5 ⏳ (Mar 1 target)

# TOTAL: 7-8 weeks from start (Nov 2024 → Dec 2024)

# ============================================================================
# SUPPORT & RESOURCES
# ============================================================================

# GitHub: https://github.com/poiley/ollama-dashboard
# Ollama: https://ollama.ai/
# Flask: https://flask.palletsprojects.com/
# Prometheus: https://prometheus.io/
# Kubernetes: https://kubernetes.io/

# ============================================================================
