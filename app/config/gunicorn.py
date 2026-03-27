# Gunicorn configuration
bind = "127.0.0.1:5000"
workers = 1
worker_class = "sync"
accesslog = "-"
errorlog = "-"
capture_output = True
timeout = 3600
loglevel = "info"

# Security settings
forwarded_allow_ips = "*"
proxy_allow_ips = "*"