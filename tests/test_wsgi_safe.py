"""Tests for WSGI-safe response headers."""
from app import create_app
from app.wsgi_safe import strip_hop_by_hop_headers
from flask import Response


def test_strip_hop_by_hop_headers_removes_connection():
    response = Response('ok')
    response.headers['Connection'] = 'keep-alive'
    response.headers['Cache-Control'] = 'no-cache'
    strip_hop_by_hop_headers(response)
    assert response.headers.get('Connection') is None
    assert response.headers.get('Cache-Control') == 'no-cache'


def test_after_request_strips_connection(tmp_path, monkeypatch):
    monkeypatch.setenv('OLLAMA_DASHBOARD_DATA', str(tmp_path))
    app = create_app('testing')

    @app.get('/probe-connection-header')
    def probe():
        response = Response('ok')
        response.headers['Connection'] = 'keep-alive'
        return response

    client = app.test_client()
    resp = client.get('/probe-connection-header')
    assert resp.status_code == 200
    assert resp.headers.get('Connection') is None
