"""Background context preload and keep-alive tracking (non-blocking)."""
from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
import time
from typing import Any

import requests

from app.services.copilot_proxy import ensure_model_context

logger = logging.getLogger(__name__)

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='copilot-prewarm')
_lock = threading.Lock()
_last_activity: dict[str, float] = {}
_preload_inflight: set[str] = set()
_default_model: str | None = None


def _keep_alive_duration() -> str:
    minutes = os.getenv('COPILOT_KEEP_ALIVE_MINUTES', '15').strip()
    try:
        m = max(int(minutes), 1)
    except ValueError:
        m = 15
    return f'{m}m'


def record_model_activity(model_name: str) -> None:
    if not model_name:
        return
    with _lock:
        _last_activity[model_name] = time.monotonic()


def schedule_context_preload(ollama_base_url: str, model_name: str, options: dict[str, Any]) -> None:
    """Fire-and-forget preload so Copilot requests never block on cold load."""
    if not model_name or not options.get('num_ctx'):
        return
    key = f'{model_name}:{options.get("num_ctx")}'
    with _lock:
        if key in _preload_inflight:
            return
        _preload_inflight.add(key)

    def _run() -> None:
        try:
            ensure_model_context(ollama_base_url, model_name, options)
        finally:
            with _lock:
                _preload_inflight.discard(key)

    _executor.submit(_run)


def schedule_startup_prewarm(ollama_base_url: str, model_name: str, options: dict[str, Any]) -> None:
    """Pre-warm default Copilot model on dashboard startup (background)."""
    if os.getenv('COPILOT_PREWARM_ON_START', 'true').strip().lower() not in ('1', 'true', 'yes'):
        return
    if not model_name:
        return
    global _default_model
    _default_model = model_name
    schedule_context_preload(ollama_base_url, model_name, options)


def touch_keep_alive(ollama_base_url: str, model_name: str) -> None:
    """Extend model residency with a lightweight keep_alive ping (debounced)."""
    if not model_name:
        return
    record_model_activity(model_name)
    if os.getenv('COPILOT_KEEP_ALIVE', 'true').strip().lower() not in ('1', 'true', 'yes'):
        return
    now = time.monotonic()
    with _lock:
        last = _last_activity.get(model_name, 0)
        if now - last < 30:
            return

    def _ping() -> None:
        try:
            requests.post(
                f'{ollama_base_url.rstrip("/")}/api/chat',
                json={
                    'model': model_name,
                    'messages': [{'role': 'user', 'content': '.'}],
                    'stream': False,
                    'keep_alive': _keep_alive_duration(),
                },
                timeout=30,
            )
        except requests.RequestException as err:
            logger.debug('Keep-alive ping failed for %s: %s', model_name, err)

    _executor.submit(_ping)


def idle_models_exceeding_timeout(idle_seconds: float) -> list[str]:
    """Return models with no recent Copilot activity (for optional unload UI)."""
    now = time.monotonic()
    with _lock:
        return [m for m, ts in _last_activity.items() if now - ts > idle_seconds]
