"""Copilot-specific helpers: context preload and request logging."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

_LOG_MAX_BYTES = 512_000


def _log_path() -> Path | None:
    base = os.getenv('OLLAMA_DASHBOARD_DATA') or os.getenv('DATA_DIR') or '.'
    try:
        path = Path(base) / 'copilot_proxy.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        return None


def log_ollama_proxy_hit(
    *,
    method: str,
    path: str,
    data_dir: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log any inbound ``/ollama`` request (helps confirm VS Code is using the proxy)."""
    base = data_dir or os.getenv('OLLAMA_DASHBOARD_DATA') or os.getenv('DATA_DIR') or '.'
    try:
        log_file = Path(base) / 'copilot_proxy.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        if log_file.exists() and log_file.stat().st_size > _LOG_MAX_BYTES:
            log_file.write_text('', encoding='utf-8')
        record: dict[str, Any] = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'kind': 'hit',
            'method': method,
            'path': path,
        }
        if extra:
            record.update(extra)
        with open(log_file, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError as err:
        logger.debug('Copilot proxy hit log failed: %s', err)


def log_copilot_request(
    payload: dict[str, Any],
    *,
    path: str,
    resolved_model: str,
    data_dir: str | None = None,
    pipeline: dict[str, Any] | None = None,
) -> None:
    """Append a truncated Copilot chat-completions record for troubleshooting."""
    base = data_dir or os.getenv('OLLAMA_DASHBOARD_DATA') or os.getenv('DATA_DIR') or '.'
    try:
        log_file = Path(base) / 'copilot_proxy.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        if log_file.exists() and log_file.stat().st_size > _LOG_MAX_BYTES:
            log_file.write_text('', encoding='utf-8')
        messages = payload.get('messages') or []
        image_count = sum(
            len(msg.get('images') or [])
            for msg in messages
            if isinstance(msg, dict) and isinstance(msg.get('images'), list)
        )
        record: dict[str, Any] = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'kind': 'chat',
            'path': path,
            'model_in': payload.get('model'),
            'model_resolved': resolved_model,
            'stream': payload.get('stream'),
            'message_count': len(messages),
            'has_tools': bool(payload.get('tools')),
            'has_images': image_count > 0,
            'image_count': image_count,
            'options_num_ctx': (payload.get('options') or {}).get('num_ctx'),
        }
        if pipeline:
            record['pipeline'] = {
                k: pipeline[k]
                for k in (
                    'routed_model', 'route_reason', 'system_prompt_injected',
                    'context_trim', 'num_ctx', 'rag',
                )
                if k in pipeline
            }
            trim = pipeline.get('context_trim') or {}
            record['context_trimmed'] = bool(trim.get('trimmed'))
        with open(log_file, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    except OSError as err:
        logger.debug('Copilot proxy log write failed: %s', err)


def _fetch_ps_models(ollama_base_url: str) -> list[dict]:
    """Return model entries from Ollama ``/api/ps`` (currently loaded in memory)."""
    if not ollama_base_url:
        return []
    try:
        response = requests.get(f'{ollama_base_url.rstrip("/")}/api/ps', timeout=8)
        response.raise_for_status()
        body = response.json()
    except requests.RequestException as err:
        logger.debug('Could not read /api/ps: %s', err)
        return []
    models = body.get('models') if isinstance(body, dict) else None
    if not isinstance(models, list):
        return []
    return [entry for entry in models if isinstance(entry, dict)]


def list_running_model_names(ollama_base_url: str) -> list[str]:
    """Names of models currently loaded in Ollama memory."""
    names: list[str] = []
    for entry in _fetch_ps_models(ollama_base_url):
        name = (entry.get('name') or entry.get('model') or '').strip()
        if name:
            names.append(name)
    return names


def loaded_context_length(ollama_base_url: str, model_name: str) -> int | None:
    """Return Ollama /api/ps context_length for ``model_name`` if loaded."""
    if not model_name:
        return None
    for entry in _fetch_ps_models(ollama_base_url):
        name = (entry.get('name') or entry.get('model') or '').strip()
        if name == model_name:
            ctx = entry.get('context_length')
            if isinstance(ctx, int) and ctx > 0:
                return ctx
            opts = entry.get('options')
            if isinstance(opts, dict) and isinstance(opts.get('num_ctx'), int):
                return opts['num_ctx']
    return None


def ensure_model_context(ollama_base_url: str, model_name: str, options: dict[str, Any]) -> None:
    """Load/reload model via native /api/chat so saved ``num_ctx`` applies before v1 chat.

    Ollama's ``/v1/chat/completions`` ignores ``options.num_ctx``; a quick native chat
    request with merged options sets the loaded context for subsequent v1 traffic.
    """
    want_ctx = options.get('num_ctx') if isinstance(options, dict) else None
    if not model_name or not want_ctx:
        return
    try:
        want_ctx = int(want_ctx)
    except (TypeError, ValueError):
        return
    current = loaded_context_length(ollama_base_url, model_name)
    if current is not None:
        if current != want_ctx:
            logger.info(
                'Model %s loaded at num_ctx=%s; saved setting is %s — '
                'use Restart model in dashboard',
                model_name, current, want_ctx,
            )
        return
    base = ollama_base_url.rstrip('/')
    try:
        requests.post(
            f'{base}/api/chat',
            json={
                'model': model_name,
                'messages': [{'role': 'user', 'content': 'hi'}],
                'stream': False,
                'keep_alive': '5m',
                'options': dict(options),
            },
            timeout=120,
        )
        logger.info(
            'Preloaded %s with num_ctx=%s before first Copilot v1 request',
            model_name, want_ctx,
        )
    except requests.RequestException as err:
        logger.warning('Context preload for %s failed: %s', model_name, err)
