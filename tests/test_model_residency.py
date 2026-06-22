"""Unit tests for multi-model RAM residency (no live Ollama required)."""
from unittest.mock import MagicMock, patch

import pytest

from app.services import model_residency as mr


@pytest.fixture(autouse=True)
def _clear_pins():
    with mr._lock:
        mr._pinned.clear()
    yield
    with mr._lock:
        mr._pinned.clear()


def test_parse_residency_env_fast_and_heavy(monkeypatch):
    monkeypatch.setenv('RESIDENCY_FAST_MODEL', 'gemma4:latest')
    monkeypatch.setenv('RESIDENCY_HEAVY_MODEL', 'qwen3.6:35b')
    monkeypatch.setenv('RESIDENCY_KEEP_ALIVE', '-1')
    specs = mr.parse_residency_env()
    assert len(specs) == 2
    assert specs[0].model == 'gemma4:latest'
    assert specs[0].role == 'fast'
    assert specs[1].model == 'qwen3.6:35b'
    assert specs[1].role == 'heavy'


def test_parse_residency_env_falls_back_to_prewarm(monkeypatch):
    monkeypatch.delenv('RESIDENCY_FAST_MODEL', raising=False)
    monkeypatch.setenv('COPILOT_PREWARM_MODEL', 'lfm2.5:latest')
    specs = mr.parse_residency_env()
    assert len(specs) == 1
    assert specs[0].model == 'lfm2.5:latest'


def test_pin_keep_alive_for_registered():
    mr.register_pin('gemma4:latest', role='fast', keep_alive=-1)
    assert mr.is_pinned('gemma4:latest')
    assert mr.pin_keep_alive_for('gemma4:latest') == -1
    assert mr.pin_keep_alive_for('other') is None


def test_unpin_removes_registry_entry():
    mr.register_pin('a', role='fast')
    assert mr.unpin_model('a')
    assert not mr.is_pinned('a')
    assert not mr.unpin_model('a')


@patch('app.services.model_residency.requests.get')
def test_get_residency_status_merges_ps(mock_get):
    mr.register_pin('gemma4:latest', role='fast', keep_alive=-1)
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {'models': [{'name': 'gemma4:latest', 'size_vram': 5_000_000_000}]},
    )
    status = mr.get_residency_status('http://127.0.0.1:11434')
    assert status['resident_fast_model'] == 'gemma4:latest'
    assert status['resident_fast_loaded'] is True
    assert 'OLLAMA_MAX_LOADED_MODELS' in status['ollama_server_env']


@patch('app.services.model_residency.requests.get')
def test_pin_model_sync_success(mock_get):
    svc = MagicMock()
    svc._session.post.return_value = MagicMock(status_code=200, text='{}')
    svc.get_default_settings.return_value = {}
    svc.get_model_settings_with_fallback.return_value = None
    result = mr.pin_model_sync(svc, 'http://127.0.0.1:11434', 'gemma4:latest', role='fast')
    assert result['success']
    assert mr.is_pinned('gemma4:latest')
    posted = svc._session.post.call_args
    assert posted[0][0].endswith('/api/generate')
    assert posted[1]['json']['keep_alive'] == -1
