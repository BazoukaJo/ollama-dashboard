"""Disk usage is collected for history/raw paths; public get_system_stats omits disk."""

import pytest


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


def test_get_system_stats_omits_disk(app):
    """Dashboard-facing stats drop disk (lighter payload); see get_disk_info for disk."""
    with app.app_context():
        service = app.config['OLLAMA_SERVICE']
        stats = service.get_system_stats()
        assert stats is not None
        assert 'disk' not in stats


def test_disk_info_available(app):
    """Low-level disk helper still exposes percent for callers that need it."""
    with app.app_context():
        service = app.config['OLLAMA_SERVICE']
        disk = service._get_disk_info()
        assert isinstance(disk, dict)
        assert 'percent' in disk
