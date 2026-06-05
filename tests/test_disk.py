"""Disk activity vs capacity: dashboard exposes busy %, not storage used."""

import time

import pytest


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


def test_get_system_stats_includes_disk_activity(app):
    """Dashboard-facing stats include SSD/disk busy % (not storage capacity)."""
    with app.app_context():
        service = app.config['OLLAMA_SERVICE']
        stats = service.get_system_stats()
        assert stats is not None
        assert 'disk' in stats
        assert 'activity_percent' in stats['disk']
        assert isinstance(stats['disk']['activity_percent'], (int, float))
        assert 0 <= stats['disk']['activity_percent'] <= 100
        assert 'percent' not in stats['disk']


def test_disk_info_available(app):
    """Low-level disk helper still exposes storage capacity for other callers."""
    with app.app_context():
        service = app.config['OLLAMA_SERVICE']
        disk = service._get_disk_info()
        assert isinstance(disk, dict)
        assert 'percent' in disk


def test_disk_activity_percent_computes_after_second_sample():
    from app.services.system_stats import get_disk_activity_percent

    get_disk_activity_percent()
    time.sleep(0.12)
    second = get_disk_activity_percent()
    assert isinstance(second, (int, float))
    assert 0 <= second <= 100
