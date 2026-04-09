"""
Smoke-test HTTP routes with the Flask test client.

Mutating Ollama routes are intentionally omitted: unmocked POSTs to start/stop/restart/pull/delete
models or to service start/stop/restart hit a real Ollama (or OS service) and can download,
unload, or delete models. Use the dedicated mocked tests in test_*model*.py for those behaviors.
"""
import logging

import pytest
from app import create_app


def get_endpoints():
    return [
        ('GET', '/'),
        ('GET', '/api/test'),
        ('GET', '/api/models/info/test-model'),
        ('GET', '/api/system/stats'),
        ('GET', '/api/models/available'),
        ('GET', '/api/models/running'),
        ('GET', '/api/models/settings/test-model'),
        ('GET', '/api/models/settings/recommended/test-model'),
        ('POST', '/api/models/settings/test-model'),
        ('DELETE', '/api/models/settings/test-model'),
        ('POST', '/api/models/settings/apply_all_recommended'),
        ('POST', '/api/models/settings/test-model/reset'),
        ('GET', '/api/version'),
        ('POST', '/api/models/bulk/start'),
        ('POST', '/api/chat'),
        ('GET', '/metrics'),
        ('GET', '/health'),
        ('GET', '/api/chat/history'),
        ('POST', '/api/chat/history'),
        ('GET', '/api/models/performance/test-model'),
        ('GET', '/api/system/stats/history'),
        ('GET', '/api/service/status'),
        ('GET', '/api/health'),
        ('GET', '/api/models/memory/usage'),
        ('GET', '/api/models/downloadable'),
        ('GET', '/api/test-models-debug'),
        ('GET', '/admin/model-defaults'),
    ]

@pytest.fixture(scope='module')
def client():
    app = create_app()
    with app.test_client() as client:
        yield client

def test_all_endpoints(client):
    endpoints = get_endpoints()
    failures = []
    for method, url in endpoints:
        if method in ('POST', 'PUT'):
            resp = getattr(client, method.lower())(url, json={})
        else:
            resp = getattr(client, method.lower())(url)
        if resp.status_code not in (200, 400, 404, 500, 501, 503):
            failures.append(f"FAIL: {method} {url} -> {resp.status_code}")
    if failures:
        logging.error("--- Endpoint Failures ---")
        for fail in failures:
            logging.error(fail)
    assert not failures, f"Some endpoints failed: {failures}"
