import json
import pytest
from app import create_app

class DummyResponse:
    status_code = 200
    def __init__(self, payload):
        self._payload = payload
    def json(self):
        return self._payload
    def raise_for_status(self):
        return None

@pytest.fixture()
def client(monkeypatch):
    app = create_app()
    client = app.test_client()
    # Patch Session.get used by service to simulate /api/tags
    sample = {
        'models': [
            {'name': 'llava'},  # should become vision True
            {'name': 'foo-tools', 'has_tools': 'yes', 'has_vision': None},  # mixed types
            {'name': 'generic-model', 'has_reasoning': 1},  # int truthy
        ]
    }
    def fake_get(self, url, timeout=10):
        # Only intercept tags endpoint
        if url.endswith('/api/tags'):
            return DummyResponse(sample)
        # Return empty models for other endpoints to avoid side effects
        return DummyResponse({'models': []})
    monkeypatch.setattr('app.services.ollama.requests.Session.get', fake_get)
    return client


def test_available_models_capabilities_normalized(client):
    resp = client.get('/api/models/available')
    assert resp.status_code == 200
    data = resp.get_json()
    models = data.get('models', []) if isinstance(data, dict) else data
    assert models, 'Expected models list'
    for m in models:
        for key in ('has_vision','has_tools','has_reasoning'):
            assert key in m, f"Missing capability flag {key}"
            assert isinstance(m[key], bool), f"Capability {key} not boolean: {m[key]!r}"
    # Specific expectations
    llava = next(x for x in models if x['name'] == 'llava')
    assert llava['has_vision'] is True
    foo = next(x for x in models if x['name'] == 'foo-tools')
    assert isinstance(foo['has_tools'], bool)
    assert isinstance(foo['has_vision'], bool)
