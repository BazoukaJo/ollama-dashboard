from app.services.ollama import OllamaService
from app import create_app
from unittest.mock import patch

ADVANCED_KEYS = [
    'num_predict','repeat_last_n','repeat_penalty','presence_penalty','frequency_penalty',
    'stop','min_p','typical_p','penalize_newline','mirostat','mirostat_tau','mirostat_eta'
]

BASIC_KEYS = ['temperature','top_k','top_p','num_ctx','seed']

ALL_KEYS = BASIC_KEYS + ADVANCED_KEYS

def test_defaults_include_advanced_keys():
    svc = OllamaService()
    defaults = svc.get_default_settings()
    for k in ALL_KEYS:
        assert k in defaults, f"Missing default key: {k}"
    # Type checks for a few
    assert isinstance(defaults['repeat_last_n'], int)
    assert isinstance(defaults['repeat_penalty'], float)
    assert isinstance(defaults['stop'], list)
    assert isinstance(defaults['penalize_newline'], bool)


def test_recommendation_preserves_keys():
    svc = OllamaService()
    model_info = {
        'name': 'qwen2.5:7b',
        'details': {'parameter_size': '7B', 'families': ['qwen']},
        'has_tools': True,
        'has_vision': False,
        'has_reasoning': False
    }
    rec = svc._recommend_settings_for_model(model_info)
    for k in ALL_KEYS:
        assert k in rec, f"Recommended missing key {k}"
    # Heuristic expectations
    assert rec['num_predict'] >= 300  # medium bucket adjustment
    assert rec['repeat_penalty'] >= 1.05  # qwen adjustment raises


def test_save_normalizes_types(tmp_path):
    app = create_app()
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / 'model_settings.json')
    from app.routes.main import ollama_service as route_service
    route_service.init_app(app)
    raw_settings = {
        'temperature': '0.55',
        'top_k': '25',
        'repeat_penalty': '1.2',
        'presence_penalty': '0.1',
        'frequency_penalty': '0.2',
        'stop': 'END,STOP',
        'penalize_newline': 'true',
        'num_predict': '300'
    }
    assert route_service.save_model_settings('extended-model', raw_settings)
    stored = route_service.get_model_settings('extended-model')['settings']
    assert isinstance(stored['temperature'], float)
    assert isinstance(stored['top_k'], int)
    assert isinstance(stored['repeat_penalty'], float)
    assert stored['stop'] == ['END','STOP']
    assert isinstance(stored['penalize_newline'], bool)
    assert stored['num_predict'] == 300


def test_chat_includes_advanced_keys(tmp_path):
    app = create_app()
    client = app.test_client()
    from app.routes.main import ollama_service as route_service
    route_service.init_app(app)
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / 'model_settings.json')
    route_service.save_model_settings('chat-model', {'temperature': 0.22, 'repeat_penalty': 1.15, 'stop': ['STOP']})

    called = {}

    class FakeResponse:
        status_code = 200
        def json(self):
            return {'response': 'ok'}

    def fake_post(url, json=None, **kwargs):
        called['json'] = json
        return FakeResponse()

    with patch('app.routes.main.ollama_service._session') as mock_session:
        mock_session.post.side_effect = fake_post
        with patch('app.routes.main.ollama_service.get_model_info_cached', return_value={'name':'chat-model'}):
            resp = client.post('/api/chat', json={'model': 'chat-model', 'prompt': 'Hello'})
    assert resp.status_code == 200
    posted = called['json']
    opts = posted['options']
    for k in ADVANCED_KEYS:
        assert k in opts, f"Chat options missing advanced key {k}"
    assert opts['temperature'] == 0.22
    assert opts['repeat_penalty'] == 1.15
    assert opts['stop'] == ['STOP']
