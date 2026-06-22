"""Sanitize error text before returning it to API clients."""
from __future__ import annotations

import logging
from typing import Any

GENERIC_UPSTREAM = (
    'The upstream service returned an error. Check server logs for details.'
)
GENERIC_CONNECTION = (
    'Cannot connect to Ollama. Ensure the service is running and retry.'
)
GENERIC_OPERATION = 'The operation failed. Check server logs for details.'


def log_upstream_error(
    log: logging.Logger,
    *,
    status_code: int | None = None,
    detail: Any = None,
    context: str = '',
) -> None:
    prefix = f'{context}: ' if context else ''
    code = f' HTTP {status_code}' if status_code is not None else ''
    log.warning('%sUpstream error%s: %s', prefix, code, detail)
