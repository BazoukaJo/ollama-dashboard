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
        posted = called.get('json')
        assert 'messages' in posted
        assert posted['messages'][0]['role'] == 'user'
        assert posted['options']['temperature'] == 0.33
        assert posted['options']['top_k'] == 77
        assert called['url'].endswith('/api/chat')


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
    user_msg = called['json']['messages'][0]
    assert 'images' in user_msg
    assert len(user_msg['images']) == 1


def test_chat_stream_returns_generator_response(tmp_path):
    """Streaming /api/chat must yield chunks incrementally, not buffer the whole body."""
    app = create_app()
    client = app.test_client()
    from app.routes.main import ollama_service as route_ollama_service
    route_ollama_service.init_app(app)
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / "model_settings.json")

    chunks = [
        json.dumps({"message": {"role": "assistant", "content": "Hello"}, "done": False}).encode() + b"\n",
        json.dumps({"message": {"role": "assistant", "content": " world"}, "done": False}).encode() + b"\n",
        json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}).encode() + b"\n",
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
    assert json.loads(lines[0])["message"]["content"] == "Hello"
    assert json.loads(lines[1])["message"]["content"] == " world"


def test_chat_accepts_multi_turn_messages(tmp_path):
    app = create_app()
    client = app.test_client()
    from app.routes.main import ollama_service as route_ollama_service
    route_ollama_service.init_app(app)
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / 'model_settings.json')

    called = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {'message': {'role': 'assistant', 'content': 'Follow-up answer'}}

    def fake_post(url, json=None, **kwargs):
        called['json'] = json
        return FakeResponse()

    messages = [
        {'role': 'user', 'content': 'First question'},
        {'role': 'assistant', 'content': 'First answer'},
        {'role': 'user', 'content': 'Follow up'},
    ]
    with patch('app.routes.main.ollama_service._session') as mock_session:
        mock_session.post.side_effect = fake_post
        with patch('app.routes.main.ollama_service.get_model_info_cached', return_value={'name': 'ml-model'}):
            resp = client.post('/api/chat', json={'model': 'ml-model', 'messages': messages})
    assert resp.status_code == 200
    assert called['json']['messages'] == messages


def test_chat_enables_thinking_for_reasoning_models(tmp_path):
    app = create_app()
    client = app.test_client()
    from app.routes.main import ollama_service as route_ollama_service
    route_ollama_service.init_app(app)
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / 'model_settings.json')

    called = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {'message': {'role': 'assistant', 'content': 'ok'}}

    def fake_post(url, json=None, **kwargs):
        called['json'] = json
        return FakeResponse()

    model = {'name': 'deepseek-r1', 'has_reasoning': True}
    with patch('app.routes.main.ollama_service._session') as mock_session:
        mock_session.post.side_effect = fake_post
        with patch('app.routes.main.ollama_service.get_model_info_cached', return_value=model):
            resp = client.post('/api/chat', json={'model': 'deepseek-r1', 'prompt': 'Think'})
    assert resp.status_code == 200
    assert called['json'].get('think') is True


def test_chat_omits_thinking_for_non_reasoning_models(tmp_path):
    app = create_app()
    client = app.test_client()
    from app.routes.main import ollama_service as route_ollama_service
    route_ollama_service.init_app(app)
    app.config['MODEL_SETTINGS_FILE'] = str(tmp_path / 'model_settings.json')

    called = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {'message': {'role': 'assistant', 'content': 'ok'}}

    def fake_post(url, json=None, **kwargs):
        called['json'] = json
        return FakeResponse()

    with patch('app.routes.main.ollama_service._session') as mock_session:
        mock_session.post.side_effect = fake_post
        with patch('app.routes.main.ollama_service.get_model_info_cached', return_value={'name': 'llama3'}):
            resp = client.post('/api/chat', json={'model': 'llama3', 'prompt': 'Hi'})
    assert resp.status_code == 200
    assert 'think' not in called['json']
