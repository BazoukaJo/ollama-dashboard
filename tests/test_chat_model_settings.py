import json
from unittest.mock import patch

from app import create_app


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

    with patch('app.routes.main.ollama_service._session') as mock_session:
        mock_session.post.side_effect = fake_post
        with patch('app.routes.main.ollama_service.get_model_info_cached', return_value={'name':'ml-model'}):
            resp = client.post('/api/chat', json={'model': 'ml-model', 'prompt': 'Hello'})
        assert resp.status_code == 200
        # The generate call used should include options with per-model overrides
        posted = called.get('json')
        assert 'options' in posted
        assert posted['options']['temperature'] == 0.33
        assert posted['options']['top_k'] == 77


def test_chat_forwards_image_attachments(tmp_path):
    app = create_app()
    client = app.test_client()
    from app.routes.main import ollama_service as route_ollama_service
    route_ollama_service.init_app(app)
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / 'model_settings.json')

    png_b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
    )
    called = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {'response': 'ok'}

    def fake_post(url, json=None, **kwargs):
        called['json'] = json
        return FakeResponse()

    model = {'name': 'llava', 'has_vision': True}
    with patch('app.routes.main.ollama_service._session') as mock_session:
        mock_session.post.side_effect = fake_post
        with patch('app.routes.main.ollama_service.get_model_info_cached', return_value=model):
            resp = client.post(
                '/api/chat',
                json={
                    'model': 'llava',
                    'prompt': 'Describe',
                    'attachments': [{'type': 'image', 'name': 'x.png', 'content': png_b64}],
                },
            )
    assert resp.status_code == 200
    assert 'images' in called['json']
    assert len(called['json']['images']) == 1


def test_chat_stream_returns_generator_response(tmp_path):
    """Streaming /api/chat must yield chunks incrementally, not buffer the whole body."""
    app = create_app()
    client = app.test_client()
    from app.routes.main import ollama_service as route_ollama_service
    route_ollama_service.init_app(app)
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / "model_settings.json")

    chunks = [
        json.dumps({"response": "Hello"}).encode() + b"\n",
        json.dumps({"response": " world"}).encode() + b"\n",
        json.dumps({"response": "", "done": True}).encode() + b"\n",
    ]

    class FakeStreamResponse:
        status_code = 200
        def iter_content(self, chunk_size=None):
            return iter(chunks)

    def fake_post(url, json=None, **kwargs):
        return FakeStreamResponse()

    with patch('app.routes.main.ollama_service._session') as mock_session:
        mock_session.post.side_effect = fake_post
        with patch('app.routes.main.ollama_service.get_model_info_cached', return_value={'name': 'ml-model'}):
            resp = client.post('/api/chat', json={'model': 'ml-model', 'prompt': 'Hi', 'stream': True})
    assert resp.status_code == 200
    body = resp.data
    lines = [ln for ln in body.split(b"\n") if ln.strip()]
    assert len(lines) == 3
    assert json.loads(lines[0])["response"] == "Hello"
    assert json.loads(lines[1])["response"] == " world"
