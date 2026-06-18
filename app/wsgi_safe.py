"""WSGI response header helpers (Waitress / PEP 3333)."""
from __future__ import annotations

from flask import Response

# Hop-by-hop headers must not be set by WSGI apps (Waitress raises AssertionError).
HOP_BY_HOP_HEADERS = frozenset({
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade',
})


def strip_hop_by_hop_headers(response: Response) -> Response:
    """Remove headers Waitress rejects before ``start_response``."""
    for key in list(response.headers.keys()):
        if key.lower() in HOP_BY_HOP_HEADERS:
            response.headers.pop(key, None)
    return response
