# Security Guide for Ollama Dashboard

---

## Input Validation

### Model Name Validation

```python
# Allowed: alphanumeric, hyphens, underscores, slashes, plus, colons, periods
# Pattern: ^[a-zA-Z0-9:._/+\-]+$

# Valid model names:
# llama3.1:8b
# llava-phi
# custom_model-v2
# my-model:latest
# VladimirGav/gemma4-26b-16GB-VRAM:latest
# repo/model+quant:latest

# Invalid model names (rejected):
# llama3.1 <script>alert(1)</script>
# model$name
# model;rm -rf /
```

### Numeric Bounds

Settings values are validated with min/max bounds:
- Temperature: 0 to 2
- Top-k: 1 to 100
- Top-p: 0 to 1
- Num predict: 1 to 10000

---

## Output Sanitization

### HTML Escaping

All user inputs are escaped before rendering in templates. Model names in JavaScript use `cssEscape()` for safe DOM queries.

### JSON Response Safety

JSON responses are automatically safe (no raw HTML injection possible).

---

## Network Security

### CORS Configuration

By default, CORS is permissive for local development. Restrict in production:

```bash
# .env
CORS_ORIGINS=http://localhost:5000,http://127.0.0.1:5000
```

### Firewall Rules (Linux)

```bash
# Allow from localhost only
sudo ufw allow from 127.0.0.1 to any port 5000

# If behind Nginx
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 5000/tcp
```

---

## HTTPS/TLS

### Self-Signed Certificate (Development)
```bash
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365
```

### Let's Encrypt (Production)
```bash
sudo certbot certonly --standalone -d dashboard.example.com
```

Use Nginx as a reverse proxy to terminate TLS in front of the dashboard.

---

## Secrets Management

### Never Commit Secrets

```bash
# .gitignore
.env
.env.local
.env.*.local
*.key
*.pem
```

### Environment Variable Security

```bash
# Use strong, random values when setting API keys
openssl rand -hex 32
```

---

## Vulnerability Scanning

### Dependency Security

```bash
pip audit

# Or use safety
pip install safety
safety check
```

### Container Scanning

```bash
# Scan Docker image with Trivy
trivy image ollama-dashboard:latest
```

### Code Scanning

```bash
# Security-focused analysis
bandit -r app/

# Static analysis
pylint app/
```

---

## Privacy & Data Protection

- No personal data collected (names, emails, etc.)
- No tracking cookies
- All data remains on-premise (not cloud-synced)
- Chat history and model settings stored locally in JSON files

---

## References

- [OWASP Top 10](https://owasp.org/Top10/)
- [Flask Security](https://flask.palletsprojects.com/security/)
