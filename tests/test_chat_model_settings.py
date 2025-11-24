from app import create_app
from unittest.mock import patch


def test_chat_uses_per_model_settings(tmp_path):
    app = create_app()
    client = app.test_client()
    # Initialize the route's shared service so endpoints and tests use the same configuration
    from app.routes.main import ollama_service as route_ollama_service
    route_ollama_service.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    # Save a per-model setting
    route_ollama_service.save_model_settings('ml-model', {'temperature': 0.33, 'top_k': 77}, source='user')

    # Patch requests.post used by chat route to capture payload
    called = {}

    class FakeResponse:
        def __init__(self):
            self.status_code = 200
        def json(self):
            return {"response": "ok"}

    def fake_post(url, json=None, **kwargs):
        called['url'] = url
        called['json'] = json
        return FakeResponse()

    with patch('app.routes.main.requests.post', side_effect=fake_post) as _:
        with patch('app.routes.main.ollama_service.get_model_info_cached', return_value={'name':'ml-model'}):
            resp = client.post('/api/chat', json={'model': 'ml-model', 'prompt': 'Hello'})
        assert resp.status_code == 200
        # The generate call used should include options with per-model overrides
        posted = called.get('json')
        assert 'options' in posted
        assert posted['options']['temperature'] == 0.33
        assert posted['options']['top_k'] == 77
