"""Shared HTTP client for proxy → Ollama upstream calls.

Uses a pooled ``requests.Session`` for keep-alive. Tests patch ``post`` / ``request``
on this module (same pattern as legacy ``requests.post`` patches).
"""
from __future__ import annotations

import requests

_session: requests.Session | None = None


def _pool() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def reset_pool() -> None:
    """Close and discard the pooled session (tests / app teardown)."""
    global _session
    if _session is not None:
        try:
            _session.close()
        except OSError:
            pass
        _session = None


def post(url: str, **kwargs):
    return _pool().post(url, **kwargs)


def request(method: str, url: str, **kwargs):
    return _pool().request(method, url, **kwargs)
