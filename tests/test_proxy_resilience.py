"""Resilience tests for the settings-injecting proxy.

The proxy must behave like a robust online provider: self-heal transient upstream failures,
keep IDE clients alive while a model loads, and *never* hang indefinitely. These tests exercise
``_NativeChatStream`` (first-token timeout, mid-stream stall guard, connection retry) directly and
end-to-end through ``/ollama/v1/chat/completions``.
"""
import time
from unittest.mock import patch

import app.routes.proxy as proxy
import requests
from app import create_app
from app.services.v1_native_bridge import STREAM_HEARTBEAT


class _BlockingStream:
    """200 OK whose iter_lines() emits given lines then blocks (simulates a stalled model)."""

    status_code = 200

    def __init__(self, lines=(), block_seconds=1.0):
        self._lines = list(lines)
        self._block_seconds = block_seconds

    def iter_lines(self):
        for line in self._lines:
            yield line
        if self._block_seconds:
            time.sleep(self._block_seconds)

    def close(self):
        pass


def test_native_stream_first_token_timeout_raises_504():
    """No token within first_token_timeout -> abort with 504 (never heartbeat forever)."""
    with patch.object(proxy, '_upstream_post', return_value=_BlockingStream(block_seconds=1.0)):
        chat_stream = proxy._NativeChatStream(
            'u', {}, heartbeat_seconds=0.05, timeout=1,
            first_token_timeout=0.3, stall_timeout=5, max_attempts=1,
        )
        saw_heartbeat = False
        err = None
        try:
            for item in chat_stream.iter_raw():
                if item is STREAM_HEARTBEAT:
                    saw_heartbeat = True
        except proxy._UpstreamStatusError as exc:
            err = exc

    assert saw_heartbeat, 'expected keep-alive heartbeats while waiting for the first token'
    assert err is not None and err.status_code == 504


def test_native_stream_midstream_stall_ends_gracefully():
    """A model that stalls after partial output ends the stream cleanly (no exception, no hang)."""
    line = b'{"message":{"role":"assistant","content":"hi"},"done":false}'
    with patch.object(proxy, '_upstream_post', return_value=_BlockingStream(lines=(line,), block_seconds=1.0)):
        chat_stream = proxy._NativeChatStream(
            'u', {}, heartbeat_seconds=0.05, timeout=1,
            first_token_timeout=5, stall_timeout=0.3, max_attempts=1,
        )
        items = list(chat_stream.iter_raw())

    assert line in items  # partial output preserved


def test_native_stream_retries_connection_error_then_recovers():
    """A connection failure before the first byte is retried automatically and recovers."""
    ok = _BlockingStream(
        lines=(b'{"message":{"role":"assistant","content":"ok"},"done":true}',),
        block_seconds=0.0,
    )
    calls = {'n': 0}

    def flaky(*_args, **_kwargs):
        calls['n'] += 1
        if calls['n'] == 1:
            raise requests.ConnectionError('connection refused')
        return ok

    with patch.object(proxy, '_upstream_post', side_effect=flaky):
        chat_stream = proxy._NativeChatStream(
            'u', {}, heartbeat_seconds=0.05, timeout=1,
            first_token_timeout=5, stall_timeout=5, max_attempts=3, retry_backoff=0.0,
        )
        err = chat_stream.peek_error(2.0)
        items = list(chat_stream.iter_raw())

    assert err is None, 'a recoverable connection error must not fail fast'
    assert calls['n'] == 2
    assert any(isinstance(i, (bytes, bytearray)) and b'ok' in i for i in items)


def test_v1_chat_self_heals_connection_error(tmp_path, monkeypatch):
    """End-to-end: a transient Ollama connection failure is retried and the turn still succeeds."""
    monkeypatch.setenv('MODEL_SETTINGS_FILE', str(tmp_path / 'model_settings.json'))
    monkeypatch.setenv('OLLAMA_HOST', 'localhost')
    monkeypatch.delenv('OLLAMA_PORT', raising=False)
    monkeypatch.setenv('AUTO_START_OLLAMA', 'false')
    monkeypatch.setenv('OLLAMA_PROXY_UPSTREAM_RETRY_BACKOFF_SECONDS', '0')

    app = create_app()
    app.config['OLLAMA_SERVICE'].save_model_settings('healme', {}, source='user')
    client = app.test_client()

    calls = {'n': 0}

    class OkStream:
        status_code = 200

        def iter_lines(self):
            yield b'{"message":{"role":"assistant","content":"hello"},"done":true}'

        def close(self):
            pass

    def flaky_post(url, json=None, **kwargs):
        if not kwargs.get('stream'):
            raise AssertionError('expected a streaming post')
        calls['n'] += 1
        if calls['n'] == 1:
            raise requests.ConnectionError('refused')
        return OkStream()

    fake_models = type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()
    with patch('requests.post', side_effect=flaky_post), patch('requests.get', return_value=fake_models):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'healme',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': True,
        })
        body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert calls['n'] == 2  # retried once, then succeeded
    assert 'hello' in body
