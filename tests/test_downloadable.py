"""Test downloadable models endpoint."""

import pytest


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


def test_get_downloadable_models_best(app):
    """get_downloadable_models('best') should return a non-empty list."""
    with app.app_context():
        service = app.config['OLLAMA_SERVICE']
        models = service.get_downloadable_models('best')
        assert isinstance(models, list)
        assert len(models) > 0
        assert 'name' in models[0]
