"""Resolve OpenAI ``model`` fields for VS Code Copilot / BYOK clients.

Recent Copilot Chat builds sometimes send a numeric model index (``"3"``) instead of
the Ollama model id string.  We map indices using the same ordering as ``GET /v1/models``.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_INDEX_RE = re.compile(r'^\d+$')
_CACHE: dict[str, tuple[float, list[str]]] = {}
_CACHE_TTL_SEC = 30.0


def _fetch_v1_model_ids(ollama_base_url: str) -> list[str]:
    url = f"{ollama_base_url.rstrip('/')}/v1/models"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    body = response.json()
    ids: list[str] = []
    for entry in body.get('data') or []:
        if isinstance(entry, dict) and entry.get('id'):
            ids.append(str(entry['id']))
    return ids


def _cached_model_ids(ollama_base_url: str) -> list[str]:
    now = time.monotonic()
    cached = _CACHE.get(ollama_base_url)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]
    try:
        ids = _fetch_v1_model_ids(ollama_base_url)
    except requests.RequestException as exc:
        logger.warning("Failed to list /v1/models for index resolution: %s", exc)
        if cached:
            return cached[1]
        return []
    _CACHE[ollama_base_url] = (now, ids)
    return ids


def resolve_v1_model_name(ollama_base_url: str, model: Any) -> str:
    """Return an Ollama model id, resolving numeric Copilot indices when needed."""
    if model is None:
        return ''
    name = str(model).strip()
    if not name or not _INDEX_RE.match(name):
        return name
    idx = int(name)
    ids = _cached_model_ids(ollama_base_url)
    if 0 <= idx < len(ids):
        resolved = ids[idx]
        logger.info("Resolved Copilot model index %s -> %s", idx, resolved)
        return resolved
    logger.warning("Copilot model index %s out of range (have %s models)", idx, len(ids))
    return name


def invalidate_model_list_cache() -> None:
    """Clear cached ``/v1/models`` lists (tests)."""
    _CACHE.clear()
