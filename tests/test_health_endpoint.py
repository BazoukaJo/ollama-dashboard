"""Health endpoint contract tests."""

import pytest
from app import create_app

@pytest.fixture(scope="module", name="app_client")
def fixture_app_client():
    """Yield a test client for the app."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client

def test_health_endpoint_structure(app_client):
    """Health payload includes expected keys and shapes."""
    resp = app_client.get('/api/health')
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
    for _, value in data['cache_age_seconds'].items():
        if value is not None:
            assert value >= 0

def test_health_endpoint_recovers_after_access(app_client):
    """Repeated access stays stable and reports failure counts."""
    # Access again to ensure repeated calls remain stable
    resp = app_client.get('/api/health')
    assert resp.status_code == 200
    data = resp.get_json()
    # Consecutive failures should not explode in test environment; allow >=0
    assert data['consecutive_ps_failures'] >= 0
