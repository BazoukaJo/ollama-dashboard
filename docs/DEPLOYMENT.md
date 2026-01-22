# Ollama Dashboard Deployment Guide

Complete deployment instructions for all environments from development to enterprise Kubernetes.

## Quick Start (5 minutes)

### Prerequisites
- Python 3.8+
- Ollama running on localhost:11434
- pip or conda

### Installation
```bash
# Clone or download the repository
cd ollama-dashboard

# Install dependencies
pip install -r requirements.txt

# Run the app
python OllamaDashboard.py

# Open in browser
open http://localhost:5000
```

---

## Environment Setup

### Configuration via Environment Variables

Create a `.env` file (not committed to git):

```bash
# Ollama connection
OLLAMA_HOST=localhost
OLLAMA_PORT=11434

# API Keys (generate strong random values)
API_KEY_VIEWER=sk-viewer-$(openssl rand -hex 16)
API_KEY_OPERATOR=sk-operator-$(openssl rand -hex 16)
API_KEY_ADMIN=sk-admin-$(openssl rand -hex 16)

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

# Optional: External monitoring
OTEL_EXPORTER_OTLP_ENDPOINT=
ALERT_WEBHOOK_URL=
```

Load environment variables before starting:
```bash
set -a
source .env
set +a
python OllamaDashboard.py
```

### Configuration Priority
1. Environment variables (highest priority)
2. `.env` file
3. Hardcoded defaults (lowest priority)

---

## Docker Deployment

### Single Container (Development)

**Dockerfile:**
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV OLLAMA_HOST=host.docker.internal
ENV OLLAMA_PORT=11434

EXPOSE 5000

CMD ["python", "OllamaDashboard.py"]
```

**Build & Run:**
```bash
# Build image
docker build -t ollama-dashboard:latest .

# Run container (connects to host Ollama)
docker run -p 5000:5000 \
  -e OLLAMA_HOST=host.docker.internal \
  -e API_KEY_ADMIN=sk-admin-... \
  ollama-dashboard:latest
```

### Docker Compose (with Ollama)

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0:11434

  dashboard:
    build: .
    container_name: ollama-dashboard
    ports:
      - "5000:5000"
    environment:
      - OLLAMA_HOST=ollama
      - OLLAMA_PORT=11434
      - API_KEY_ADMIN=sk-admin-changeme
    depends_on:
      - ollama
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs

volumes:
  ollama_data:
```

**Run:**
```bash
docker-compose up -d
# Access at http://localhost:5000
```

---

## Gunicorn + Nginx (Production)

### Install Gunicorn
```bash
pip install gunicorn
```

### Gunicorn Configuration

**gunicorn_config.py:**
```python
# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes: (2 * CPU cores) + 1
workers = 5

# Worker class
worker_class = "sync"
worker_connections = 1000
timeout = 30

# Logging
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"

# Process naming
proc_name = "ollama-dashboard"

# Keep-alive
keepalive = 2

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None
```

**Run Gunicorn:**
```bash
gunicorn \
  --config gunicorn_config.py \
  --env OLLAMA_HOST=localhost \
  --env API_KEY_ADMIN=sk-admin-... \
  wsgi:app
```

### Nginx Configuration

**nginx.conf:**
```nginx
upstream ollama_dashboard {
    server 127.0.0.1:5000;
}

server {
    listen 80;
    server_name dashboard.example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name dashboard.example.com;

    # SSL certificates
    ssl_certificate /etc/ssl/certs/dashboard.crt;
    ssl_certificate_key /etc/ssl/private/dashboard.key;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Logging
    access_log /var/log/nginx/ollama-dashboard.access.log;
    error_log /var/log/nginx/ollama-dashboard.error.log;

    # Proxy settings
    location / {
        proxy_pass http://ollama_dashboard;
        proxy_http_version 1.1;

        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Keep-alive
        proxy_set_header Connection "";
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }

    # Static files (cache longer)
    location /static/ {
        proxy_pass http://ollama_dashboard;
        proxy_cache_valid 200 1d;
        expires 1d;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://ollama_dashboard;
        proxy_read_timeout 5s;
    }
}
```

**Start Nginx:**
```bash
nginx -c /etc/nginx/nginx.conf
```

---

## Kubernetes Deployment

### Prerequisites
- Kubernetes cluster (1.20+)
- kubectl configured
- Helm (optional, but recommended)

### Kubernetes Manifests

**k8s/namespace.yaml:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ollama-dashboard
```

**k8s/configmap.yaml:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ollama-dashboard-config
  namespace: ollama-dashboard
data:
  OLLAMA_HOST: "ollama-service"
  OLLAMA_PORT: "11434"
  LOG_LEVEL: "INFO"
```

**k8s/secret.yaml:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ollama-dashboard-secrets
  namespace: ollama-dashboard
type: Opaque
stringData:
  API_KEY_VIEWER: "sk-viewer-replace-with-strong-key"
  API_KEY_OPERATOR: "sk-operator-replace-with-strong-key"
  API_KEY_ADMIN: "sk-admin-replace-with-strong-key"
```

**k8s/deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama-dashboard
  namespace: ollama-dashboard
  labels:
    app: ollama-dashboard
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0

  selector:
    matchLabels:
      app: ollama-dashboard

  template:
    metadata:
      labels:
        app: ollama-dashboard
    spec:
      containers:
      - name: dashboard
        image: ollama-dashboard:latest
        imagePullPolicy: IfNotPresent

        ports:
        - containerPort: 5000
          name: http
          protocol: TCP

        envFrom:
        - configMapRef:
            name: ollama-dashboard-config
        - secretRef:
            name: ollama-dashboard-secrets

        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi

        # Health checks
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3

        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        volumeMounts:
        - name: data
          mountPath: /app/data
        - name: logs
          mountPath: /app/logs

      volumes:
      - name: data
        emptyDir: {}
      - name: logs
        emptyDir: {}
```

**k8s/service.yaml:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: ollama-dashboard
  namespace: ollama-dashboard
  labels:
    app: ollama-dashboard
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 5000
    protocol: TCP
    name: http
  selector:
    app: ollama-dashboard
```

**k8s/hpa.yaml (Horizontal Pod Autoscaler):**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ollama-dashboard-hpa
  namespace: ollama-dashboard
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ollama-dashboard
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

**k8s/ingress.yaml:**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ollama-dashboard-ingress
  namespace: ollama-dashboard
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - dashboard.example.com
    secretName: ollama-dashboard-tls
  rules:
  - host: dashboard.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: ollama-dashboard
            port:
              number: 80
```

### Deploy to Kubernetes

```bash
# Create namespace and secrets
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# Deploy application
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# Deploy ingress
kubectl apply -f k8s/ingress.yaml

# Check status
kubectl get pods -n ollama-dashboard
kubectl logs -f deployment/ollama-dashboard -n ollama-dashboard

# Port forward for testing
kubectl port-forward svc/ollama-dashboard 5000:80 -n ollama-dashboard
# Access at http://localhost:5000
```

---

## Helm Deployment (Optional)

### Helm Chart Structure
```
helm/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-prod.yaml
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── configmap.yaml
    ├── secret.yaml
    ├── hpa.yaml
    └── ingress.yaml
```

**Install:**
```bash
helm install ollama-dashboard ./helm \
  --namespace ollama-dashboard \
  --create-namespace \
  -f helm/values-prod.yaml
```

---

## Monitoring & Observability

### Prometheus Integration

**prometheus.yml:**
```yaml
scrape_configs:
  - job_name: 'ollama-dashboard'
    static_configs:
      - targets: ['localhost:5000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Grafana Dashboard

Import [dashboards/ollama-dashboard.json](../dashboards/ollama-dashboard.json):
1. Open Grafana
2. Dashboards → Import
3. Upload JSON file
4. Select Prometheus data source
5. Save

### Log Aggregation

**ELK Stack Example (Logstash configuration):**
```
input {
  file {
    path => "/var/log/ollama-dashboard/audit.log"
    codec => json
  }
}

filter {
  mutate {
    add_field => { "[@metadata][index_name]" => "ollama-audit-%{+YYYY.MM.dd}" }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "%{[@metadata][index_name]}"
  }
}
```

---

## Scaling Strategies

### Vertical Scaling (Bigger Machine)
- Increase CPU/memory limits in Kubernetes
- Increase Gunicorn workers
- Use larger connection pool

### Horizontal Scaling (More Machines)
- Deploy multiple dashboard instances
- Use load balancer (Nginx, HAProxy, Kubernetes Service)
- Shared Redis cache (recommended)
- Shared database for settings

### Database Backend (Recommended for 50+ instances)
```python
# Switch from JSON to PostgreSQL
pip install psqlalchemy
# Update OllamaService to use SQLAlchemy models
```

---

## Troubleshooting Deployment

| Issue | Solution |
|-------|----------|
| Dashboard can't connect to Ollama | Check `OLLAMA_HOST` env var; ensure Ollama API is accessible |
| High memory usage | Reduce cache TTL; use Redis backend for sharing cache |
| Slow model start | Increase timeout; check network latency |
| Settings changes not saving | Check file permissions; ensure disk space available |
| API key errors | Verify `API_KEY_*` env vars are set; check audit log |

---

## Security Best Practices

1. **Use Strong API Keys**
   ```bash
   # Generate random 32-byte key
   openssl rand -hex 32
   ```

2. **Enable HTTPS**
   - Use Let's Encrypt (free SSL)
   - Nginx + cert-manager in Kubernetes

3. **Restrict CORS Origins**
   - Set `CORS_ORIGINS` to trusted domains only
   - Default: localhost only

4. **Enable Audit Logging**
   - Set `AUDIT_LOG_FILE` path
   - Rotate logs regularly
   - Monitor for suspicious activity

5. **Network Security**
   - Run Ollama on private network
   - Dashboard behind firewall
   - Use VPN for remote access

6. **Regular Updates**
   - Keep Python dependencies updated
   - Use Docker image scanning (Trivy, Snyk)
   - Subscribe to security alerts

---

## Backup & Restore

### Backup
```bash
# Backup settings and history
tar czf ollama-dashboard-backup-$(date +%Y%m%d).tar.gz \
  history.json \
  model_settings.json \
  logs/
```

### Restore
```bash
# Extract backup
tar xzf ollama-dashboard-backup-20240115.tar.gz

# Restart app
python OllamaDashboard.py
```

---

## Performance Tuning

### For 10-50 Users
- Single Flask process
- In-memory cache
- Local JSON files
- ✅ Works out of box

### For 50-500 Users
- Gunicorn with 4-8 workers
- Redis cache
- Nginx load balancing
- PostgreSQL for settings
- Estimated: $20-50/month cloud infrastructure

### For 500+ Users
- Kubernetes cluster (3+ nodes)
- Distributed cache (Redis Cluster)
- Managed PostgreSQL (AWS RDS, Azure Database)
- CDN for static assets
- Estimated: $200-500/month

---

## Cleanup

### Stop Deployment
```bash
# Docker Compose
docker-compose down

# Kubernetes
kubectl delete namespace ollama-dashboard

# Gunicorn
pkill -f gunicorn
```

### Delete Data
```bash
# Local
rm -f history.json model_settings.json
rm -rf data/ logs/

# Docker volumes
docker volume rm ollama-dashboard_ollama_data
```

---

## Support & Issues

- **Documentation**: [docs/README.md](README.md)
- **Issues**: [GitHub Issues](https://github.com/poiley/ollama-dashboard/issues)
- **Community**: [Ollama Discord](https://discord.gg/ollama)
