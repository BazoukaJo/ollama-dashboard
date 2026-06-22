"""Upstream HTTP helpers for the /ollama proxy blueprint."""
from __future__ import annotations

import os
import time
from typing import Optional

import requests
from flask import current_app

from app.services import upstream_http
from app.wsgi_safe import HOP_BY_HOP_HEADERS

_UPSTREAM_CONNECT_TIMEOUT = 30
_UPSTREAM_STREAM_READ_TIMEOUT = 3600
_UPSTREAM_STREAM_TIMEOUT = (_UPSTREAM_CONNECT_TIMEOUT, _UPSTREAM_STREAM_READ_TIMEOUT)
_UPSTREAM_INFERENCE_TIMEOUT = 120
_UPSTREAM_DEFAULT_TIMEOUT = 30
_DEFAULT_STREAM_HEARTBEAT_SECONDS = 5.0
_DEFAULT_STREAM_FIRST_BYTE_GRACE_SECONDS = 3.0


def env_float(name, default, *, minimum, maximum):
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def env_int(name, default, *, minimum, maximum):
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def stream_heartbeat_seconds():
    return env_float(
        'OLLAMA_PROXY_STREAM_HEARTBEAT_SECONDS',
        _DEFAULT_STREAM_HEARTBEAT_SECONDS,
        minimum=1.0,
        maximum=60.0,
    )


def stream_first_byte_grace_seconds():
    return env_float(
        'OLLAMA_PROXY_STREAM_FIRST_BYTE_GRACE_SECONDS',
        _DEFAULT_STREAM_FIRST_BYTE_GRACE_SECONDS,
        minimum=0.5,
        maximum=30.0,
    )


def stream_first_token_timeout_seconds():
    return env_float(
        'OLLAMA_PROXY_FIRST_TOKEN_TIMEOUT_SECONDS', 300.0, minimum=15.0, maximum=3600.0,
    )


def stream_stall_timeout_seconds():
    return env_float(
        'OLLAMA_PROXY_STREAM_STALL_TIMEOUT_SECONDS', 120.0, minimum=5.0, maximum=3600.0,
    )


def upstream_max_attempts():
    return env_int('OLLAMA_PROXY_UPSTREAM_MAX_ATTEMPTS', 3, minimum=1, maximum=6)


def upstream_retry_backoff_seconds():
    return env_float('OLLAMA_PROXY_UPSTREAM_RETRY_BACKOFF_SECONDS', 0.4, minimum=0.0, maximum=5.0)


def copilot_keep_alive():
    if os.getenv('COPILOT_KEEP_ALIVE', 'true').strip().lower() not in ('1', 'true', 'yes'):
        return None
    raw = os.getenv('COPILOT_KEEP_ALIVE_MINUTES', '15').strip()
    try:
        minutes = max(int(raw), 1)
    except ValueError:
        minutes = 15
    return f'{minutes}m'


def upstream_post(url, payload, *, stream=False, timeout=None):
    if timeout is None:
        timeout = _UPSTREAM_STREAM_TIMEOUT if stream else _UPSTREAM_INFERENCE_TIMEOUT
    return upstream_http.post(url, json=payload, stream=stream, timeout=timeout)


def upstream_post_with_retry(url, payload, *, stream=False, timeout=None):
    attempts = upstream_max_attempts()
    backoff = upstream_retry_backoff_seconds()
    last_err: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return upstream_post(url, payload, stream=stream, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
            last_err = err
            if attempt < attempts:
                time.sleep(backoff * attempt)
                continue
            raise
    if last_err is not None:
        raise last_err
    raise RuntimeError('upstream POST failed without connecting')  # pragma: no cover


def upstream_request(method, url, **kwargs):
    timeout = kwargs.pop('timeout', _UPSTREAM_DEFAULT_TIMEOUT)
    return upstream_http.request(
        method=method,
        url=url,
        allow_redirects=False,
        timeout=timeout,
        **kwargs,
    )


def filter_upstream_response_headers(headers):
    safe = []
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower in HOP_BY_HOP_HEADERS:
            continue
        if key_lower in ('content-encoding', 'content-length'):
            continue
        safe.append((key, value))
    return safe


def ollama_url():
    svc = current_app.config['OLLAMA_SERVICE']
    host, port = svc.get_ollama_host_port()
    return f'http://{host}:{port}'
