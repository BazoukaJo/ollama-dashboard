"""Shared warm-start payload and POST helper for loading models into memory."""
from __future__ import annotations

from typing import Any

import requests

from app.services.service_errors import HTTP_SERVICE_ERRORS

_WARM_ERRORS = HTTP_SERVICE_ERRORS


def build_warm_start_payload(
    svc: Any,
    model_name: str,
    *,
    prompt: str = 'Hello',
    keep_alive: str = '24h',
) -> dict[str, Any]:
    """Build a generate payload with merged per-model settings."""
    payload: dict[str, Any] = {
        'model': model_name,
        'prompt': prompt,
        'stream': False,
        'keep_alive': keep_alive,
    }
    try:
        options = svc.get_default_settings()
        entry = svc.get_model_settings_with_fallback(model_name)
        if entry and isinstance(entry.get('settings'), dict):
            options.update(entry['settings'])
        payload['options'] = options
    except _WARM_ERRORS:
        pass
    return payload


def post_warm_start(
    svc: Any,
    generate_url: str,
    model_name: str,
    *,
    prompt: str = 'Hello',
    timeout: int = 120,
) -> requests.Response:
    """POST a warm-start generate request to load *model_name* into memory."""
    payload = build_warm_start_payload(svc, model_name, prompt=prompt)
    return svc._session.post(generate_url, json=payload, timeout=timeout)
