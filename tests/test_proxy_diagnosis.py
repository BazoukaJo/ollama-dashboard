"""Tests for the 'Connection Doctor' diagnosis classifier and route."""
import json

from app import create_app
from app.services.copilot_analytics import diagnose_recent_activity


def _write_log(tmp_path, records):
    log = tmp_path / 'copilot_proxy.log'
    log.write_text('\n'.join(json.dumps(r) for r in records) + '\n', encoding='utf-8')


def test_diagnosis_no_activity(tmp_path):
    result = diagnose_recent_activity(tmp_path)
    assert result['category'] == 'no_activity'


def test_diagnosis_first_token_timeout(tmp_path):
    _write_log(tmp_path, [
        {'ts': '2026-01-01T00:00:00+00:00', 'kind': 'chat', 'model_in': 'qwen3:14b', 'model_resolved': 'qwen3:14b'},
        {'ts': '2026-01-01T00:05:00+00:00', 'kind': 'response', 'model': 'qwen3:14b', 'error': 'upstream_status_504', 'content_chars': 0, 'tool_calls': 0},
    ])
    result = diagnose_recent_activity(tmp_path)
    assert result['category'] == 'first_token_timeout'
    assert 'qwen3:14b' in result['message']


def test_diagnosis_connection_error(tmp_path):
    _write_log(tmp_path, [
        {'ts': '2026-01-01T00:00:00+00:00', 'kind': 'chat', 'model_in': 'qwen3:14b', 'model_resolved': 'qwen3:14b'},
        {'ts': '2026-01-01T00:00:01+00:00', 'kind': 'response', 'model': 'qwen3:14b', 'error': 'ConnectionError', 'content_chars': 0, 'tool_calls': 0},
    ])
    result = diagnose_recent_activity(tmp_path)
    assert result['category'] == 'connection_error'


def test_diagnosis_agent_degeneracy(tmp_path):
    _write_log(tmp_path, [
        {'ts': '2026-01-01T00:00:00+00:00', 'kind': 'chat', 'model_in': 'gemma4:31b', 'model_resolved': 'gemma4:31b'},
        {
            'ts': '2026-01-01T00:02:00+00:00', 'kind': 'response', 'model': 'gemma4:31b',
            'agent': True, 'content_chars': 1, 'tool_calls': 0, 'error': None,
        },
    ])
    result = diagnose_recent_activity(tmp_path)
    assert result['category'] == 'agent_degeneracy'


def test_diagnosis_context_trimmed(tmp_path):
    _write_log(tmp_path, [
        {
            'ts': '2026-01-01T00:00:00+00:00', 'kind': 'chat', 'model_in': 'qwen3:14b', 'model_resolved': 'qwen3:14b',
            'pipeline': {'context_trim': {'trimmed': True, 'tokens_before': 12000, 'tokens_after': 6000}},
            'context_trimmed': True,
        },
        {
            'ts': '2026-01-01T00:00:05+00:00', 'kind': 'response', 'model': 'qwen3:14b',
            'content_chars': 400, 'tool_calls': 0, 'error': None,
        },
    ])
    result = diagnose_recent_activity(tmp_path)
    assert result['category'] == 'context_trimmed'
    assert '12000' in result['message']
    assert '6000' in result['message']


def test_diagnosis_ok(tmp_path):
    _write_log(tmp_path, [
        {'ts': '2026-01-01T00:00:00+00:00', 'kind': 'chat', 'model_in': 'qwen3:14b', 'model_resolved': 'qwen3:14b'},
        {
            'ts': '2026-01-01T00:00:05+00:00', 'kind': 'response', 'model': 'qwen3:14b',
            'content_chars': 400, 'tool_calls': 0, 'error': None, 'finish_reason': 'stop',
        },
    ])
    result = diagnose_recent_activity(tmp_path)
    assert result['category'] == 'ok'


def test_diagnosis_route(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTO_START_OLLAMA', 'false')
    app = create_app()
    app.config['DATA_DIR'] = str(tmp_path)
    _write_log(tmp_path, [
        {'ts': '2026-01-01T00:00:00+00:00', 'kind': 'chat', 'model_in': 'qwen3:14b', 'model_resolved': 'qwen3:14b'},
        {
            'ts': '2026-01-01T00:00:05+00:00', 'kind': 'response', 'model': 'qwen3:14b',
            'content_chars': 400, 'tool_calls': 0, 'error': None, 'finish_reason': 'stop',
        },
    ])
    client = app.test_client()
    resp = client.get('/api/proxy/diagnosis')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['category'] == 'ok'
