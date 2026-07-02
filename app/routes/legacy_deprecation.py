"""HTTP deprecation helpers for legacy /api/copilot/* and /ollama/copilot-debug routes."""
from __future__ import annotations

from flask import Response, request


def apply_legacy_deprecation(response: Response, successor_path: str) -> Response:
    """Attach RFC 8594-style deprecation headers to a legacy route response."""
    response.headers['Deprecation'] = 'true'
    response.headers['Link'] = f'<{successor_path}>; rel="successor-version"'
    response.headers['Warning'] = f'299 - "Deprecated; use {successor_path} instead."'
    return response


def copilot_api_successor_path() -> str | None:
    """Map ``/api/copilot/...`` to ``/api/proxy/...`` when the current request is legacy."""
    path = request.path
    if not path.startswith('/api/copilot/'):
        return None
    return path.replace('/api/copilot/', '/api/proxy/', 1)


def maybe_deprecate_copilot_api(response: Response) -> Response:
    successor = copilot_api_successor_path()
    if successor:
        return apply_legacy_deprecation(response, successor)
    return response
