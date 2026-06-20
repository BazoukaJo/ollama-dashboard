"""Tests for client proxy extras persistence."""
from app import create_app
from app.services.copilot_extras import normalize_client_extras


def test_copilot_think_defaults_off():
    assert normalize_client_extras(None)['copilot_think'] == 'off'
    assert normalize_client_extras({})['copilot_think'] == 'off'


def test_copilot_think_accepts_known_modes():
    for mode in ('off', 'auto', 'on'):
        assert normalize_client_extras({'copilot_think': mode})['copilot_think'] == mode


def test_copilot_think_coerces_aliases_and_garbage():
    assert normalize_client_extras({'copilot_think': True})['copilot_think'] == 'on'
    assert normalize_client_extras({'copilot_think': 'enabled'})['copilot_think'] == 'on'
    assert normalize_client_extras({'copilot_think': 'false'})['copilot_think'] == 'off'
    assert normalize_client_extras({'copilot_think': 'banana'})['copilot_think'] == 'off'


def test_copilot_think_round_trips_through_save(tmp_path, monkeypatch):
    monkeypatch.setenv('MODEL_SETTINGS_FILE', str(tmp_path / 'model_settings.json'))
    app = create_app()
    svc = app.config['OLLAMA_SERVICE']
    svc.save_model_settings(
        'gemma4:31b',
        {'temperature': 0.6, 'num_ctx': 16384},
        source='user',
        copilot={'copilot_think': 'on'},
    )
    body = app.test_client().get('/api/models/settings?model=gemma4:31b').get_json()
    assert body['client']['copilot_think'] == 'on'


def test_partial_client_save_preserves_tuned_settings(tmp_path, monkeypatch):
    """A client-only save must not reset a model's tuned num_ctx/sampling to defaults."""
    monkeypatch.setenv('MODEL_SETTINGS_FILE', str(tmp_path / 'model_settings.json'))
    app = create_app()
    svc = app.config['OLLAMA_SERVICE']
    svc.save_model_settings(
        'gemma4:31b',
        {'temperature': 0.6, 'num_ctx': 16384, 'num_predict': 8192},
        source='user',
    )
    # Partial update: only the proxy/client block (mirrors what a client extras POST sends).
    svc.save_model_settings('gemma4:31b', {}, source='user', copilot={'copilot_think': 'on'})
    entry = svc.get_model_settings_with_fallback('gemma4:31b')
    assert entry['settings']['num_ctx'] == 16384
    assert entry['settings']['num_predict'] == 8192
    assert entry['settings']['temperature'] == 0.6
    assert entry['client']['copilot_think'] == 'on'


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
