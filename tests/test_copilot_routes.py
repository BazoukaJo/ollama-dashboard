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
    status = client.get('/api/copilot/status')
    assert status.status_code == 200
    assert status.headers.get('Deprecation') == 'true'
    assert '/api/proxy/status' in (status.headers.get('Link') or '')

    wizard = client.get('/api/copilot/wizard-checks')
    assert wizard.status_code == 200
    assert wizard.headers.get('Deprecation') == 'true'
    assert '/api/proxy/wizard-checks' in (wizard.headers.get('Link') or '')


def test_legacy_copilot_debug_route_deprecation():
    app = create_app()
    client = app.test_client()
    resp = client.get('/ollama/copilot-debug')
    assert resp.status_code == 200
    assert resp.headers.get('Deprecation') == 'true'
    assert '/ollama/proxy-debug' in (resp.headers.get('Link') or '')


def test_advisor_recommend():
    app = create_app()
    client = app.test_client()
    resp = client.get('/api/advisor/recommend')
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'recommended_models' in body
    assert 'proxy_base_url' in body
