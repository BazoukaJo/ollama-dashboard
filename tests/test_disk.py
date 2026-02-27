"""Test system stats API — disk stats specifically."""

import pytest
from unittest.mock import patch


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


def test_system_stats_includes_disk(app):
    """System stats should include disk percent."""
    with app.app_context():
        service = app.config['OLLAMA_SERVICE']
        stats = service.get_system_stats()
        assert stats is not None
        assert 'disk' in stats
        assert 'percent' in stats['disk']
