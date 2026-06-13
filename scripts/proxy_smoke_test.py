#!/usr/bin/env python3
"""Smoke checks for the /ollama API proxy (in-process, no live Ollama required)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class _FakeStream:
    status_code = 200

    def iter_content(self, chunk_size=1024):
        return iter([b'data: {"choices":[]}\n\n'])


def main() -> int:
    from app import create_app

    app = create_app('development')
    client = app.test_client()

    r = client.get('/ollama')
    if r.status_code != 200:
        print('proxy_smoke: /ollama expected 200, got', r.status_code, file=sys.stderr)
        return 1

    r_status = client.get('/api/proxy/status')
    if r_status.status_code != 200:
        print('proxy_smoke: status endpoint failed', file=sys.stderr)
        return 1

    r_wiz = client.get('/api/proxy/wizard-checks')
    if r_wiz.status_code != 200:
        print('proxy_smoke: wizard checks failed', file=sys.stderr)
        return 1

    with patch('app.routes.proxy._upstream_post', return_value=_FakeStream()):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'test-model',
            'messages': [{'role': 'user', 'content': 'hello'}],
            'stream': True,
        })
        if resp.status_code != 200:
            print('proxy_smoke: v1 chat proxy failed', resp.status_code, file=sys.stderr)
            return 1
        resp.get_data()

    print('proxy_smoke: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
