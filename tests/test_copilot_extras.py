"""Tests for client proxy extras persistence."""
from app import create_app


def test_save_and_read_client_extras(tmp_path, monkeypatch):
    monkeypatch.setenv('MODEL_SETTINGS_FILE', str(tmp_path / 'model_settings.json'))
    app = create_app()
    svc = app.config['OLLAMA_SERVICE']
    svc.save_model_settings(
        'qwen-test',
        {'temperature': 0.3, 'num_ctx': 16384},
        source='user',
        copilot={'system_prompt_preset': 'coding_assistant', 'context_trim_enabled': True},
    )
    entry = svc.get_model_settings_with_fallback('qwen-test')
    assert entry['settings']['num_ctx'] == 16384
    assert entry['client']['system_prompt_preset'] == 'coding_assistant'

    client = app.test_client()
    resp = client.get('/api/models/settings?model=qwen-test')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['client']['system_prompt_preset'] == 'coding_assistant'


def test_legacy_copilot_key_still_readable(tmp_path, monkeypatch):
    import json
    path = tmp_path / 'model_settings.json'
    path.write_text(json.dumps({
        'legacy-model': {
            'settings': {'num_ctx': 8192},
            'copilot': {'system_prompt_preset': 'reviewer'},
            'source': 'user',
        }
    }), encoding='utf-8')
    monkeypatch.setenv('MODEL_SETTINGS_FILE', str(path))
    app = create_app()
    resp = app.test_client().get('/api/models/settings?model=legacy-model')
    body = resp.get_json()
    assert body['client']['system_prompt_preset'] == 'reviewer'
