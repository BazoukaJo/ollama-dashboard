"""Tests for benchmark-backed recommendation profiles."""
from app import create_app
from app.services.model_recommendation_profiles import match_recommendation_profile
from app.services.ollama import OllamaService


def _svc(tmp_path):
    app = create_app()
    svc = OllamaService()
    svc.init_app(app)
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / 'model_settings.json')
    svc.get_system_stats = lambda: {
        'memory': {'total': 64 * 1024 ** 3},
        'vram': {'total': 24 * 1024 ** 3},
    }
    return svc


def test_qwen3_profile_matches_official_sampling(tmp_path):
    svc = _svc(tmp_path)
    rec = svc._recommend_settings_for_model({
        'name': 'qwen3:14b',
        'details': {'parameter_size': '14B', 'families': ['qwen']},
        'context_length': 131072,
    })
    assert rec['temperature'] == 0.6
    assert rec['top_p'] == 0.95
    assert rec['top_k'] == 20
    assert rec['repeat_penalty'] == 1.0
    assert rec['num_ctx'] >= 8192


def test_deepseek_r1_profile(tmp_path):
    svc = _svc(tmp_path)
    rec = svc._recommend_settings_for_model({
        'name': 'deepseek-r1:8b',
        'details': {'parameter_size': '8B'},
        'context_length': 65536,
    })
    assert rec['temperature'] == 0.6
    assert rec['top_p'] == 0.95
    assert rec['repeat_penalty'] == 1.0


def test_coder_profile_is_deterministic(tmp_path):
    svc = _svc(tmp_path)
    rec = svc._recommend_settings_for_model({
        'name': 'qwen2.5-coder:7b',
        'details': {'parameter_size': '7B'},
        'context_length': 32768,
    })
    assert rec['temperature'] <= 0.25
    assert rec['repeat_penalty'] >= 1.1
    assert rec['num_predict'] >= 4096


def test_match_profile_qwen36_and_gemma4():
    assert match_recommendation_profile({'name': 'qwen3.6:35b'})['id'] == 'qwen3_thinking'
    assert match_recommendation_profile({'name': 'gemma4:latest'})['id'] == 'vision_multimodal'
    assert match_recommendation_profile({'name': 'lfm2.5:latest'})['id'] == 'reasoning_thinking'
    assert match_recommendation_profile({'name': 'nemotron3:33b'})['id'] == 'reasoning_thinking'


def test_match_profile_coding_before_general_qwen():
    profile = match_recommendation_profile({'name': 'qwen3-coder:30b'})
    assert profile is not None
    assert profile['id'] == 'coding_specialist'


def test_openai_error_sse_lines():
    from app.services.v1_native_bridge import openai_error_sse_lines
    lines = list(openai_error_sse_lines('boom', status_code=503, model='m'))
    assert len(lines) == 2
    assert lines[0].startswith('data: ')
    assert 'boom' in lines[0]
    assert lines[1].strip() == 'data: [DONE]'


def test_apply_all_skips_user_saved_models(tmp_path):
    from unittest.mock import patch

    from app import create_app

    app = create_app()
    client = app.test_client()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / 'model_settings.json'
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)
    svc.save_model_settings('user-model', {'temperature': 0.11, 'num_ctx': 99999}, source='user')

    with patch('app.routes.main._get_ollama_service', return_value=svc):
        with patch.object(svc, 'get_available_models', return_value=[
            {'name': 'user-model'},
            {'name': 'fresh-model'},
        ]):
            resp = client.post('/api/models/settings/apply_all_recommended')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data.get('skipped') == 1
    loaded = svc.load_model_settings()
    user_entry = loaded.get('user-model')
    assert isinstance(user_entry, dict)
    assert user_entry.get('settings', {}).get('num_ctx') == 99999
    assert 'fresh-model' in loaded
