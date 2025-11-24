import json
import pytest
from app import create_app

@pytest.fixture(scope="module")
def test_client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint_structure(test_client):
    resp = test_client.get('/api/health')
    assert resp.status_code == 200
    data = resp.get_json()
    # Required top-level keys
    for key in [
        'background_thread_alive',
        'consecutive_ps_failures',
        'last_background_error',
        'cache_age_seconds',
        'stale_flags'
    ]:
        assert key in data, f"Missing key {key} in health response"

    assert isinstance(data['background_thread_alive'], bool)
    assert isinstance(data['consecutive_ps_failures'], int)
    assert isinstance(data['cache_age_seconds'], dict)
    assert isinstance(data['stale_flags'], dict)

    # Expected cache age keys
    expected_age_keys = {'system_stats','running_models','available_models','ollama_version'}
    assert expected_age_keys.issubset(set(data['cache_age_seconds'].keys()))
    assert expected_age_keys.issubset(set(data['stale_flags'].keys()))

    # Ages should be None or non-negative numbers
    for k, v in data['cache_age_seconds'].items():
        if v is not None:
            assert v >= 0

def test_health_endpoint_recovers_after_access(test_client):
    # Access again to ensure repeated calls remain stable
    resp = test_client.get('/api/health')
    assert resp.status_code == 200
    data = resp.get_json()
    # Consecutive failures should not explode in test environment; allow >=0
    assert data['consecutive_ps_failures'] >= 0
