"""Tests for MCP status and wizard API fields."""
from app import create_app


def test_mcp_status_endpoint():
    app = create_app()
    client = app.test_client()
    resp = client.get('/api/mcp/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'mcp_base_url' in data
    assert data['mcp_base_url'].endswith('/mcp')
    assert 'tools' in data
    assert isinstance(data['tools'], list)
    assert data['tool_count'] >= 5


def test_wizard_payload_includes_mcp_fields():
    app = create_app()
    client = app.test_client()
    resp = client.get('/api/proxy/wizard-checks')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('mcp_base_url', '').endswith('/mcp')
    assert 'mcp_tools' in data
    assert 'mcp_client_examples' in data
    check_names = {c['name'] for c in data.get('checks') or []}
    assert 'mcp_endpoint' in check_names
