"""Test the downloadable models API endpoint."""

import pytest


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def test_downloadable_endpoint_returns_models(client):
    """GET /api/models/downloadable?category=best should return models."""
    response = client.get('/api/models/downloadable?category=best')
    assert response.status_code == 200
    data = response.get_json()
    assert 'models' in data
    assert len(data['models']) > 0
    assert 'name' in data['models'][0]
