"""Tests for external API proxy routes."""
from app import create_app


def test_proxy_status_endpoint():
    app = create_app()
    client = app.test_client()
    resp = client.get('/api/proxy/status')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get('ok') is True
    assert 'proxy_base_url' in body


def test_proxy_wizard_checks():
    app = create_app()
    client = app.test_client()
    resp = client.get('/api/proxy/wizard-checks')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'checks' in body
    assert body.get('proxy_base_url', '').endswith('/ollama')
    assert body.get('client_examples')


def test_legacy_copilot_routes_still_work():
    app = create_app()
    client = app.test_client()
    assert client.get('/api/copilot/status').status_code == 200
    assert client.get('/api/copilot/wizard-checks').status_code == 200


def test_advisor_recommend():
    app = create_app()
    client = app.test_client()
    resp = client.get('/api/advisor/recommend')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'recommended_models' in body
    assert 'proxy_base_url' in body
