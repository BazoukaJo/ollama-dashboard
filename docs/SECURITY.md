# Security Guide for Ollama Dashboard

Comprehensive security practices for production deployments.

---

## Authentication & Authorization

### API Key Setup

Generate strong API keys using OpenSSL:

```bash
# Generate 32-byte (256-bit) random keys
openssl rand -hex 32

# Example output:
# a7f2c8d9e1b4f6a3c5d7e9f1b3d5f7a9c1e3f5a7b9d1f3e5a7c9e1b3d5f7a9
```

### Setting API Keys

```bash
# .env file
API_KEY_VIEWER=sk-viewer-a7f2c8d9e1b4f6a3c5d7e9f1b3d5f7a9c1e3f5a7b9d1f3e5a7c9e1b3d5f7a9
API_KEY_OPERATOR=sk-operator-c5d7e9f1b3d5f7a9c1e3f5a7b9d1f3e5a7c9e1b3d5f7a9c1e3f5a7b9d1f3e5
API_KEY_ADMIN=sk-admin-e9f1b3d5f7a9c1e3f5a7b9d1f3e5a7c9e1b3d5f7a9c1e3f5a7b9d1f3e5a7c9
```

### Role-Based Access Control

Three roles with different permissions:

| Role | Permissions | Use Case |
|------|------------|----------|
| `viewer` | GET endpoints only | Monitoring, read-only dashboards |
| `operator` | GET + POST (start/stop models) | Team members running inference |
| `admin` | All (DELETE, service control) | System administrators |

**Example API calls:**

```bash
# As viewer (can list models, view stats)
curl -H "Authorization: Bearer sk-viewer-..." \
  http://localhost:5000/api/models/running

# As operator (can start/stop models)
curl -X POST -H "Authorization: Bearer sk-operator-..." \
  http://localhost:5000/api/models/start/llama3.1:8b

# As admin (can delete models, control service)
curl -X DELETE -H "Authorization: Bearer sk-admin-..." \
  http://localhost:5000/api/models/delete/old-model
```

### API Key Rotation

To rotate keys without downtime:

```bash
# 1. Generate new keys
NEW_VIEWER=$(openssl rand -hex 32)
NEW_OPERATOR=$(openssl rand -hex 32)
NEW_ADMIN=$(openssl rand -hex 32)

# 2. Update .env file with new values
# 3. Both old and new keys work (optional transition period)
# 4. Announce rotation to users
# 5. After grace period, remove old keys from .env
# 6. Restart application

# .env (with both old and new keys during transition)
API_KEY_VIEWER=sk-viewer-old|sk-viewer-new
# ... repeat for other roles
```

---

## Network Security

### HTTPS/TLS Configuration

#### Self-Signed Certificate (Development)
```bash
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365
```

#### Let's Encrypt (Production)
```bash
# Using Certbot
sudo certbot certonly --standalone -d dashboard.example.com

# Certificates in /etc/letsencrypt/live/dashboard.example.com/
# Update Nginx to use these certificates
```

#### Nginx SSL Configuration
```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/letsencrypt/live/dashboard.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dashboard.example.com/privkey.pem;

    # Strong security settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
}
```

### CORS Configuration

Restrict to trusted origins only:

```bash
# .env
# Default (localhost only)
CORS_ORIGINS=http://localhost:5000,http://127.0.0.1:5000

# For specific domain
CORS_ORIGINS=https://dashboard.example.com

# Multiple trusted origins
CORS_ORIGINS=https://dashboard.example.com,https://internal.example.com,http://192.168.1.100:5000
```

### Firewall Rules

#### Development (Local Network)
```bash
# Allow from localhost only
sudo ufw allow from 127.0.0.1 to any port 5000
```

#### Production (Behind Nginx)
```bash
# Only allow Nginx proxy
sudo ufw allow 443/tcp    # HTTPS to Nginx
sudo ufw allow 80/tcp     # HTTP to Nginx (redirect)
sudo ufw deny 5000/tcp    # Block direct Flask access
```

#### Kubernetes NetworkPolicy
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ollama-dashboard-netpolicy
  namespace: ollama-dashboard
spec:
  podSelector:
    matchLabels:
      app: ollama-dashboard
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 5000
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 11434  # Ollama API
```

---

## Input Validation

### Model Name Validation

```python
# Allowed: alphanumeric, hyphens, underscores, colons, periods
# Pattern: ^[a-zA-Z0-9:._-]+$

# Valid model names:
# ✓ llama3.1:8b
# ✓ llava-phi
# ✓ custom_model-v2
# ✓ my-model:latest

# Invalid model names:
# ✗ llama3.1 <script>alert(1)</script>
# ✗ model$name
# ✗ model;rm -rf /
```

### Numeric Bounds

```python
# Temperature: 0 to 2 (float)
# Top-k: 1 to 100 (integer)
# Top-p: 0 to 1 (float)
# Num predict: 1 to 10000 (integer)

# Validation examples:
if temperature < 0 or temperature > 2:
    return {"error": "temperature must be between 0 and 2"}, 400

if top_k < 1 or top_k > 100:
    return {"error": "top_k must be between 1 and 100"}, 400
```

### JSON Payload Validation

```python
# Using Pydantic (automatic validation)
from pydantic import BaseModel, Field

class StartModelRequest(BaseModel):
    model_name: str = Field(..., min_length=1, max_length=255)
    timeout: int = Field(default=60, ge=1, le=300)

# Flask route with validation
from flask import request

@app.route('/api/models/start', methods=['POST'])
def start_model():
    try:
        req = StartModelRequest(**request.json)
    except ValidationError as e:
        return {"error": str(e)}, 400
```

---

## Output Sanitization

### HTML Escaping

All user inputs escaped before rendering:

```python
from html import escape

# Model names in HTML
model_name = escape(model_name)  # "llama<script>" → "llama&lt;script&gt;"
```

### JSON Response Safety

JSON responses are automatically safe (no raw HTML):

```json
{
    "success": true,
    "models": [
        {
            "name": "llama3.1:8b",
            "description": "Escaped if needed: &lt;script&gt;"
        }
    ]
}
```

### Content Security Policy (CSP)

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;" always;
```

---

## Audit Logging

### Enabling Audit Logs

```bash
# .env
AUDIT_LOG_FILE=logs/audit.log
```

### Audit Log Format

All security events logged as JSON:

```json
{
    "timestamp": "2024-01-15T10:30:45.123Z",
    "event": "AUTH_SUCCESS",
    "ip": "192.168.1.100",
    "role": "operator",
    "endpoint": "/api/models/start/llama3.1:8b",
    "method": "POST",
    "user_agent": "curl/7.85.0"
}
```

### Log Rotation

```bash
# Rotate logs daily, keep 30 days
logrotate -f /etc/logrotate.d/ollama-dashboard

# /etc/logrotate.d/ollama-dashboard
/app/logs/audit.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    create 0640 www-data www-data
}
```

### Log Analysis

```bash
# Find failed auth attempts
grep AUTH_FAILED logs/audit.log

# Count by IP
grep AUTH_FAILED logs/audit.log | jq -r '.ip' | sort | uniq -c | sort -rn

# Find privilege escalation attempts (viewer trying admin operation)
grep AUTH_DENIED logs/audit.log | jq '.ip'
```

---

## Secrets Management

### Never Commit Secrets

```bash
# .gitignore
.env
.env.local
.env.*.local
logs/
data/
*.key
*.pem
```

### Environment Variable Security

```bash
# Use strong, random values
# Generate with: openssl rand -hex 32

# Never use default values in production
❌ API_KEY_ADMIN=admin123
✓ API_KEY_ADMIN=a7f2c8d9e1b4f6a3c5d7e9f1b3d5f7a9c1e3f5a7b9d1f3e5a7c9e1b3d5f7a9
```

### Secrets in Kubernetes

```bash
# Create secret from file
kubectl create secret generic ollama-dashboard-secrets \
  --from-file=.env \
  -n ollama-dashboard

# Mount as environment
envFrom:
- secretRef:
    name: ollama-dashboard-secrets
```

### External Secret Management (Optional)

For enterprise deployments, use:
- **HashiCorp Vault**: Centralized secrets management
- **AWS Secrets Manager**: AWS-native secrets
- **Azure Key Vault**: Azure-native secrets
- **Google Cloud Secret Manager**: GCP-native secrets

```python
# Example: Vault integration
import hvac

client = hvac.Client(url='http://vault:8200')
secret = client.secrets.kv.read_secret_version(path='ollama-dashboard')
api_key = secret['data']['data']['API_KEY_ADMIN']
```

---

## Rate Limiting

### HTTP-Level Rate Limiting

Enabled by default (5 ops/min, 2 pulls/5min):

```python
# Per-IP rate limiting
@app.before_request
def rate_limit():
    ip = request.remote_addr
    key = f"rate_limit:{ip}"
    requests = redis.incr(key)
    if requests == 1:
        redis.expire(key, 60)  # 60-second window
    if requests > 100:  # 100 requests per minute
        return {"error": "Rate limit exceeded"}, 429
```

### Burst Protection

```bash
# .env
RATE_LIMIT_BURST=10         # Allow 10 requests initially
RATE_LIMIT_REFILL=1         # Refill 1 request per second
RATE_LIMIT_WINDOW=60        # Per 60-second window
```

---

## Vulnerability Scanning

### Dependency Security

```bash
# Check for known vulnerabilities
pip audit

# Or use safety
pip install safety
safety check

# Generate Software Bill of Materials (SBOM)
pip install cyclonedx-bom
cyclonedx-bom -o sbom.xml
```

### Container Scanning

```bash
# Scan Docker image with Trivy
trivy image ollama-dashboard:latest

# Or Snyk
snyk container test ollama-dashboard:latest
```

### Code Scanning

```bash
# Static analysis with Pylint
pylint app/

# Security-focused analysis with Bandit
bandit -r app/

# Type checking with mypy
mypy app/
```

---

## Incident Response

### If Compromised

1. **Immediately rotate API keys:**
   ```bash
   # Generate new keys
   export API_KEY_ADMIN=$(openssl rand -hex 32)
   # Restart app with new env vars
   ```

2. **Review audit logs:**
   ```bash
   grep AUTH_SUCCESS logs/audit.log | tail -100
   ```

3. **Check for unauthorized changes:**
   ```bash
   git log --oneline app/
   git diff HEAD~10 app/
   ```

4. **Revoke access if breached:**
   ```bash
   # Change CORS_ORIGINS
   # Regenerate all API keys
   # Restart application
   ```

### Reporting Security Issues

Please report security vulnerabilities responsibly:
- Email: security@example.com
- GitHub Security Advisory: (private disclosure)
- Do NOT open public GitHub issues for security bugs

---

## Compliance & Standards

### OWASP Top 10 Coverage

| Vulnerability | Status | Details |
|---|---|---|
| A01: Broken Access Control | ✅ Mitigated | RBAC, auth middleware |
| A02: Cryptographic Failures | ✅ Mitigated | HTTPS, secure API keys |
| A03: Injection | ✅ Mitigated | Input validation, parameterized queries |
| A04: Insecure Design | ✅ Mitigated | Security-first architecture |
| A05: Security Misconfiguration | ✅ Mitigated | Secure defaults, env validation |
| A06: Vulnerable Components | ✅ Monitored | Dependency scanning, updates |
| A07: Identification & Auth | ✅ Mitigated | Strong API keys, audit logging |
| A08: Software & Data Integrity | ✅ Mitigated | Atomic file writes, integrity checks |
| A09: Logging & Monitoring | ✅ Implemented | Audit logs, health checks, metrics |
| A10: SSRF | ✅ Protected | Restricted to localhost Ollama |

### Privacy & Data Protection

- No personal data collected (names, emails, etc.)
- No tracking cookies
- All data remains on-premise (not cloud-synced)
- Optional: Audit logs can be deleted per retention policy

### Accessibility & Compliance

- WCAG 2.1 AA compliance (dark mode, keyboard navigation)
- SOC 2 Type II ready (audit logging, change tracking)
- HIPAA-eligible (encryption, audit trails, access controls)

---

## Security Checklist for Production

- [ ] Generate strong API keys (32-byte random)
- [ ] Set `CORS_ORIGINS` to trusted domains only
- [ ] Enable HTTPS with valid TLS certificate
- [ ] Configure firewall rules (block direct port 5000)
- [ ] Enable audit logging (`AUDIT_LOG_FILE`)
- [ ] Set up log rotation
- [ ] Run dependency vulnerability scan (`pip audit`)
- [ ] Run static analysis (`bandit`, `pylint`, `mypy`)
- [ ] Test authentication/authorization
- [ ] Test rate limiting
- [ ] Monitor logs regularly
- [ ] Plan API key rotation schedule
- [ ] Document incident response procedures
- [ ] Regular security updates (monthly)

---

## Additional Resources

- [OWASP Top 10](https://owasp.org/Top10/)
- [Flask Security](https://flask.palletsprojects.com/security/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [CIS Controls](https://www.cisecurity.org/controls/)
