"""Tests for synthetic model filtering in proxy status."""
from app.services.copilot_analytics import _is_synthetic_model, client_proxy_status


def test_is_synthetic_model():
    assert _is_synthetic_model('test-model')
    assert _is_synthetic_model('copilot-test')
    assert _is_synthetic_model('qwen-test')
    assert not _is_synthetic_model('qwen3:14b')
    assert not _is_synthetic_model('llama3.2:latest')


def test_status_skips_synthetic_last_model(tmp_path):
    log = tmp_path / 'copilot_proxy.log'
    log.write_text(
        '{"ts":"2026-01-01T00:00:00+00:00","kind":"chat","model_in":"qwen3:14b","model_resolved":"qwen3:14b"}\n'
        '{"ts":"2026-01-02T00:00:00+00:00","kind":"chat","model_in":"test-model","model_resolved":"test-model"}\n',
        encoding='utf-8',
    )
    status = client_proxy_status(tmp_path)
    assert status['last_model_logged'] == 'qwen3:14b'
    assert status['last_model'] is None
    assert status['model_loaded'] is False


def test_status_model_loaded_when_in_ps(tmp_path, monkeypatch):
    log = tmp_path / 'copilot_proxy.log'
    log.write_text(
        '{"ts":"2026-01-01T00:00:00+00:00","kind":"chat","model_in":"lfm2.5:latest","model_resolved":"lfm2.5:latest"}\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(
        'app.services.copilot_proxy.list_running_model_names',
        lambda _url: ['lfm2.5:latest'],
    )
    monkeypatch.setattr(
        'app.services.copilot_proxy.loaded_context_length',
        lambda _url, _model: 8192,
    )
    status = client_proxy_status(tmp_path, ollama_base_url='http://localhost:11434')
    assert status['model_loaded'] is True
    assert status['last_model'] == 'lfm2.5:latest'
    assert status['allocated_ctx'] == 8192


def test_status_ready_when_no_models_loaded_despite_log(tmp_path, monkeypatch):
    log = tmp_path / 'copilot_proxy.log'
    log.write_text(
        '{"ts":"2026-01-01T00:00:00+00:00","kind":"chat","model_in":"lfm2.5:latest","model_resolved":"lfm2.5:latest"}\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(
        'app.services.copilot_proxy.list_running_model_names',
        lambda _url: [],
    )
    status = client_proxy_status(tmp_path, ollama_base_url='http://localhost:11434')
    assert status['model_loaded'] is False
    assert status['last_model'] is None
    assert status['last_model_logged'] == 'lfm2.5:latest'
    assert status['loaded_model'] is None
    assert status['allocated_ctx'] is None
