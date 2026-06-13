"""Thread-safe mtime cache for model_settings.json reads in the hot proxy path."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_cache: dict[str, Any] = {'path': '', 'mtime': 0.0, 'data': {}}


def load_settings_file(settings_path: Path) -> dict[str, Any]:
    """Return parsed settings dict; reload when file mtime changes."""
    path = settings_path.resolve()
    key = str(path)
    try:
        mtime = path.stat().st_mtime if path.is_file() else 0.0
    except OSError:
        mtime = 0.0

    with _lock:
        if _cache['path'] == key and _cache['mtime'] == mtime:
            return dict(_cache['data'])

    data: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            data = {}

    with _lock:
        _cache['path'] = key
        _cache['mtime'] = mtime
        _cache['data'] = data
    return dict(data)


def invalidate_settings_cache() -> None:
    """Clear cache after writes (optional; mtime check usually suffices)."""
    with _lock:
        _cache['mtime'] = 0.0
