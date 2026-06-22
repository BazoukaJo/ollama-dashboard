"""Tests for Copilot prewarm and keep-alive helpers."""
from unittest.mock import patch

from app.services import copilot_prewarm as cp


def test_touch_keep_alive_debounces(monkeypatch):
    monkeypatch.setenv('COPILOT_KEEP_ALIVE', 'true')
    cp._last_keep_alive.clear()
    submitted = []

    class FakeExecutor:
        def submit(self, fn):
            submitted.append(fn)
            return None

    monkeypatch.setattr(cp, '_executor', FakeExecutor())
    with patch('app.services.copilot_prewarm.requests.post'):
        cp.touch_keep_alive('http://127.0.0.1:11434', 'qwen3:8b')
        cp.touch_keep_alive('http://127.0.0.1:11434', 'qwen3:8b')
    assert len(submitted) == 1


def test_schedule_context_preload_skips_without_num_ctx():
    cp._preload_inflight.clear()
    cp.schedule_context_preload('http://127.0.0.1:11434', 'm', {})
    assert not cp._preload_inflight
