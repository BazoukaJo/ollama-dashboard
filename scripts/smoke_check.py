#!/usr/bin/env python3
"""In-process smoke test: no network server; validates app factory and core API routes."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from app import create_app

    app = create_app("development")
    client = app.test_client()

    r = client.get("/api/test")
    if r.status_code != 200:
        print("smoke_check: /api/test expected 200, got", r.status_code, file=sys.stderr)
        return 1
    body = r.get_json(silent=True)
    if not body or "message" not in body:
        print("smoke_check: /api/test bad JSON", file=sys.stderr)
        return 1

    r404 = client.get("/api/nonexistent-smoke-route-xyz")
    if r404.status_code != 404:
        print("smoke_check: expected 404 for unknown API route", file=sys.stderr)
        return 1
    err_body = r404.get_json(silent=True)
    if not err_body or not (err_body.get("error") or err_body.get("message")):
        print("smoke_check: 404 response should be JSON for /api/*", file=sys.stderr)
        return 1

    r_html = client.get("/nonexistent-page-smoke-xyz")
    if r_html.status_code != 404:
        print("smoke_check: expected 404 for unknown page", file=sys.stderr)
        return 1
    if "text/html" not in (r_html.content_type or ""):
        print("smoke_check: non-API 404 should be HTML", file=sys.stderr)
        return 1
    if b"Not Found" not in r_html.data and b"not found" not in r_html.data.lower():
        print("smoke_check: HTML 404 body expected", file=sys.stderr)
        return 1

    print("smoke_check: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
