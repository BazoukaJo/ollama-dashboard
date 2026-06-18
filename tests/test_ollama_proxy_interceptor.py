"""Regression tests for the dashboard's built-in Ollama settings-injecting proxy
(`intercept_ollama_parameters` / `proxy_general_ollama_calls` in app/__init__.py).

These routes forward `/ollama/api/...` requests to the real Ollama, merging each
model's saved settings (model_settings.json) into the request's `options` — so
external clients (VS Code, `ollama run`, curl, etc.) pointed at `<host>/ollama` get
the same values the dashboard applies to its own requests. Each test below guards
against a way that merge can silently produce nothing or land on the wrong server:
merging the whole stored entry instead of its inner "settings" dict, resolving
settings_path against the wrong base directory, and double-porting the upstream URL
when OLLAMA_HOST itself carries a port.
"""
from unittest.mock import patch

from app import create_app


class FakeUpstream:
    """Stands in for requests.post(..., stream=True): status_code + iter_content()."""
    status_code = 200

    def iter_content(self, chunk_size=1024):
        return iter([b'{"message": {"role": "assistant", "content": "hi"}}'])


class FakeUpstreamResponse:
    """Stands in for requests.request(...): status_code + content + headers."""
    status_code = 200
    content = b'{"models": []}'
    headers = {'Content-Type': 'application/json'}


def _create_app_for_proxy_tests(tmp_path, monkeypatch, ollama_host='localhost', model_name=None, settings=None):
    """Build an app wired to an isolated model_settings.json and a chosen OLLAMA_HOST.

    The proxy blueprint (app/routes/proxy.py) resolves settings_path and ollama_url
    at request time from current_app.config, so env vars only need to be set before
    create_app() — which populates app.config from them — not before each request.
    """
    monkeypatch.setenv('MODEL_SETTINGS_FILE', str(tmp_path / "model_settings.json"))
    monkeypatch.setenv('OLLAMA_HOST', ollama_host)
    monkeypatch.delenv('OLLAMA_PORT', raising=False)
    app = create_app()
    if model_name is not None:
        svc = app.config['OLLAMA_SERVICE']
        svc.save_model_settings(model_name, settings or {}, source='user')
    return app


def test_intercept_chat_merges_only_inner_settings_dict(tmp_path, monkeypatch):
    """Saved values win and arrive flat in `options` — never wrapped in the stored
    entry's settings/source/last_updated envelope (regression for the 'merged the
    whole stored entry' bug)."""
    app = _create_app_for_proxy_tests(
        tmp_path, monkeypatch,
        model_name='qwen-test', settings={'temperature': 0.6, 'top_k': 20, 'num_ctx': 16384},
    )
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['url'] = url
        captured['json'] = json
        return FakeUpstream()

    with patch('requests.post', side_effect=fake_post):
        resp = client.post('/ollama/api/chat', json={
            'model': 'qwen-test',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'options': {'temperature': 0.9, 'extra_client_opt': 'keep-me'},
        })
        resp.get_data()  # drain the streamed generator so requests.post actually fires

    assert resp.status_code == 200
    assert captured['url'] == 'http://localhost:11434/api/chat'
    options = captured['json']['options']
    assert options['temperature'] == 0.6  # saved value wins over the client's 0.9
    assert options['top_k'] == 20
    assert options['num_ctx'] == 16384  # saved num_ctx wins over default 8192
    assert options['extra_client_opt'] == 'keep-me'  # client-only keys survive the merge
    for leaked_key in ('settings', 'source', 'last_updated'):
        assert leaked_key not in options


def test_intercept_generate_reads_the_same_settings_file_the_dashboard_uses(tmp_path, monkeypatch):
    """The proxy must resolve MODEL_SETTINGS_FILE the same way model_settings_file_path()
    does (bare filename against CWD), not DATA_DIR-joined — otherwise it reads a path
    that's never created and silently injects nothing (regression for the 'wrong
    settings file path' bug)."""
    app = _create_app_for_proxy_tests(
        tmp_path, monkeypatch, model_name='gen-test', settings={'seed': 42, 'temperature': 0.2},
    )
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        return FakeUpstream()

    with patch('requests.post', side_effect=fake_post):
        resp = client.post('/ollama/api/generate', json={'model': 'gen-test', 'prompt': 'hi'})
        resp.get_data()

    assert resp.status_code == 200
    assert captured['json']['options']['seed'] == 42
    assert captured['json']['options']['temperature'] == 0.2


def test_intercept_forwards_to_embedded_port_in_ollama_host(tmp_path, monkeypatch):
    """OLLAMA_HOST="127.0.0.1:11436" (the form Ollama itself expects, and the form a
    port-takeover proxy setup relies on to relocate the real Ollama) must forward to
    127.0.0.1:11436 — not the naive-concatenation http://127.0.0.1:11436:11434
    (regression for the 'double-ported ollama_url' bug)."""
    app = _create_app_for_proxy_tests(
        tmp_path, monkeypatch, ollama_host='127.0.0.1:11436',
        model_name='port-test', settings={'temperature': 0.5},
    )
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['url'] = url
        return FakeUpstream()

    with patch('requests.post', side_effect=fake_post):
        resp = client.post('/ollama/api/chat', json={'model': 'port-test', 'messages': []})
        resp.get_data()

    assert resp.status_code == 200
    assert captured['url'] == 'http://127.0.0.1:11436/api/chat'


def test_proxy_general_ollama_calls_forwards_to_embedded_port(tmp_path, monkeypatch):
    """Same embedded-port regression for the generic catchall route (used for
    /api/tags, /api/ps, /api/show, pulls, etc. — everything but chat/generate)."""
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, ollama_host='127.0.0.1:11436')
    client = app.test_client()
    captured = {}

    def fake_request(method=None, url=None, **kwargs):
        captured['method'] = method
        captured['url'] = url
        return FakeUpstreamResponse()

    with patch('requests.request', side_effect=fake_request):
        resp = client.get('/ollama/api/tags')

    assert resp.status_code == 200
    assert captured['method'] == 'GET'
    assert captured['url'] == 'http://127.0.0.1:11436/api/tags'


def test_proxy_general_strips_hop_by_hop_headers(tmp_path, monkeypatch):
    """Ollama hop-by-hop headers must not reach the WSGI response (Waitress 500)."""
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch)
    client = app.test_client()

    class ChunkyUpstream(FakeUpstreamResponse):
        headers = {
            'Content-Type': 'application/json',
            'Transfer-Encoding': 'chunked',
            'Connection': 'keep-alive',
        }

    with patch('requests.request', return_value=ChunkyUpstream()):
        resp = client.get('/ollama/api/tags')

    assert resp.status_code == 200
    assert resp.headers.get('Transfer-Encoding') is None
    assert resp.headers.get('Connection') is None
    assert 'application/json' in (resp.headers.get('Content-Type') or '')


def test_proxy_ollama_root_returns_json(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch)
    client = app.test_client()
    resp = client.get('/ollama')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('success') is True
    assert '/ollama/api/tags' in data.get('message', '')


def test_intercept_saved_num_ctx_overrides_client_and_default(tmp_path, monkeypatch):
    """Saved num_ctx in model_settings.json wins over client options and the 8192 default."""
    app = _create_app_for_proxy_tests(
        tmp_path, monkeypatch,
        model_name='ctx-test', settings={'temperature': 0.4, 'num_ctx': 32768},
    )
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        return FakeUpstream()

    with patch('requests.post', side_effect=fake_post):
        resp = client.post('/ollama/api/chat', json={
            'model': 'ctx-test',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'options': {'num_ctx': 8192},
        })
        resp.get_data()

    assert resp.status_code == 200
    options = captured['json']['options']
    assert options['temperature'] == 0.4
    assert options['num_ctx'] == 32768


def test_v1_models_passthrough(tmp_path, monkeypatch):
    """VS Code Copilot lists models via GET /v1/models."""
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch)
    client = app.test_client()
    captured = {}

    def fake_request(method=None, url=None, **kwargs):
        captured['url'] = url
        return FakeUpstreamResponse()

    with patch('requests.request', side_effect=fake_request):
        resp = client.get('/ollama/v1/models')

    assert resp.status_code == 200
    assert captured['url'] == 'http://localhost:11434/v1/models'


def test_v1_chat_completions_resolves_numeric_model_index(tmp_path, monkeypatch):
    """Copilot may send model index strings; map via /v1/models ordering."""
    from app.services.v1_model_resolve import invalidate_model_list_cache

    invalidate_model_list_cache()
    app = _create_app_for_proxy_tests(
        tmp_path, monkeypatch,
        model_name='qwen3:14b', settings={'num_ctx': 16384},
    )
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['url'] = url
        captured['json'] = json
        if kwargs.get('stream'):
            class StreamResp:
                status_code = 200
                def iter_lines(self):
                    yield b'{"message":{"role":"assistant","content":"hi"},"done":true}'
            return StreamResp()
        class Resp:
            status_code = 200
            content = b'{}'
            headers = {'Content-Type': 'application/json'}
            def json(self):
                return {'message': {'content': 'hi'}}
        return Resp()

    def fake_fetch(_base):
        return ['gemma4:latest', 'gpt-oss:20b', 'qwen3:14b']

    with patch('requests.post', side_effect=fake_post), \
         patch('requests.get', return_value=type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()), \
         patch('app.services.v1_model_resolve._fetch_v1_model_ids', side_effect=fake_fetch):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': '2',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': True,
        })
        resp.get_data()

    assert captured['url'] == 'http://localhost:11434/api/chat'
    assert captured['json']['model'] == 'qwen3:14b'
    assert captured['json']['options']['num_ctx'] == 16384


def test_v1_chat_completions_bridges_to_native_api_chat(tmp_path, monkeypatch):
    """Copilot chat is bridged to native /api/chat with merged options and output cap."""
    app = _create_app_for_proxy_tests(
        tmp_path, monkeypatch,
        model_name='copilot-test', settings={'temperature': 0.55, 'num_ctx': 16384},
    )
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['url'] = url
        captured['json'] = json
        if kwargs.get('stream'):
            class StreamResp:
                status_code = 200
                def iter_lines(self):
                    yield b'{"message":{"role":"assistant","content":"ok"},"done":true}'
            return StreamResp()
        class Resp:
            status_code = 200
            content = b'{}'
            headers = {'Content-Type': 'application/json'}
            def json(self):
                return {'message': {'role': 'assistant', 'content': 'ok'}, 'done': True}
        return Resp()

    with patch('requests.post', side_effect=fake_post), \
         patch('requests.get', return_value=type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'copilot-test',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': True,
            'parallel_tool_calls': True,
            'max_completion_tokens': 50000,
        })
        resp.get_data()

    assert resp.status_code == 200
    assert captured['url'] == 'http://localhost:11434/api/chat'
    assert captured['json']['options']['temperature'] == 0.55
    assert captured['json']['options']['num_ctx'] == 16384
    assert captured['json']['options']['num_predict'] == 16384


def test_v1_chat_non_stream_truncates_huge_response(tmp_path, monkeypatch):
    """Non-streaming bridged /api/chat responses are capped for IDE clients."""
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, model_name='cap-test', settings={})
    client = app.test_client()

    class Resp:
        status_code = 200
        content = b'{}'
        headers = {'Content-Type': 'application/json'}

        def json(self):
            return {
                'model': 'cap-test',
                'message': {'role': 'assistant', 'content': 'z' * 200_000},
                'done': True,
            }

    with patch('requests.post', return_value=Resp()), \
         patch('requests.get', return_value=type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'cap-test',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': False,
        })

    assert resp.status_code == 200
    body = resp.get_json()
    content = body['choices'][0]['message']['content']
    assert 'truncated by ollama-dashboard proxy' in content
    assert len(content) < 200_000


def test_v1_chat_stream_upstream_error_returns_sse(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, model_name='missing', settings={})
    client = app.test_client()

    class FailStream:
        status_code = 503
        text = 'model not found'
        reason = 'Service Unavailable'

        def iter_lines(self):
            return iter([])

    def fake_post(url, json=None, **kwargs):
        if kwargs.get('stream'):
            return FailStream()
        raise AssertionError('expected streaming post')

    with patch('requests.post', side_effect=fake_post):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'missing',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': True,
        })
        body = resp.get_data(as_text=True)

    assert resp.status_code == 503
    assert 'text/event-stream' in (resp.headers.get('Content-Type') or '')
    assert 'model not found' in body
    assert 'data: [DONE]' in body


def test_v1_chat_uses_settings_fallback_without_saved_entry(tmp_path, monkeypatch):
    """Proxy should apply recommended defaults like dashboard Ask when no saved entry."""
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch)
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        if kwargs.get('stream'):
            class StreamResp:
                status_code = 200
                def iter_lines(self):
                    yield b'{"message":{"role":"assistant","content":"ok"},"done":true}'
            return StreamResp()
        raise AssertionError('expected streaming post')

    recommended = {'num_ctx': 32768, 'temperature': 0.7, 'num_predict': 2048}

    with patch('requests.post', side_effect=fake_post), \
         patch('requests.get', return_value=type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()), \
         patch(
             'app.routes.proxy.compute_fresh_recommended_settings_entry',
             return_value={'settings': recommended, 'source': 'recommended'},
         ):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'brand-new-model:latest',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': True,
        })
        resp.get_data()

    assert resp.status_code == 200
    options = captured['json']['options']
    assert options.get('num_ctx') == 32768
    assert options.get('num_predict') == 2048


def test_v1_chat_non_stream_upstream_error_is_openai_shaped(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, model_name='cap-test', settings={})
    client = app.test_client()

    class FailResp:
        status_code = 400
        text = '{"error":"bad request"}'
        reason = 'Bad Request'
        content = text.encode()
        headers = {'Content-Type': 'application/json'}

        def json(self):
            return {'error': 'bad request'}

    with patch('requests.post', return_value=FailResp()), \
         patch('requests.get', return_value=type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'cap-test',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': False,
        })

    assert resp.status_code == 400
    body = resp.get_json()
    assert body['error']['type'] == 'upstream_error'
    assert 'bad request' in body['error']['message']


def test_native_api_chat_normalizes_multimodal_content(tmp_path, monkeypatch):
    """Open WebUI / tools on /ollama/api/chat get Ollama-native images[] format."""
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, model_name='vl-test', settings={'num_ctx': 8192})
    client = app.test_client()
    captured = {}
    b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        return FakeUpstream()

    with patch('requests.post', side_effect=fake_post):
        resp = client.post('/ollama/api/chat', json={
            'model': 'vl-test',
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': 'What color?'},
                    {'type': 'input_image', 'image_url': f'data:image/png;base64,{b64}'},
                ],
            }],
            'stream': True,
        })
        resp.get_data()

    msg = captured['json']['messages'][0]
    assert msg['content'] == 'What color?'
    assert msg['images'] == [b64]


def test_native_api_chat_stream_upstream_error_propagates_status(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, model_name='err-test', settings={})
    client = app.test_client()

    class FailStream:
        status_code = 404
        text = 'model not found'
        reason = 'Not Found'
        content = b'{"error":"model not found"}'

        def iter_content(self, chunk_size=1024):
            return iter([self.content])

    with patch('requests.post', return_value=FailStream()):
        resp = client.post('/ollama/api/chat', json={
            'model': 'err-test',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': True,
        })
        resp.get_data()

    assert resp.status_code == 404
    assert resp.headers.get('Access-Control-Allow-Origin') == '*'


def test_native_api_chat_settings_fallback(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch)
    client = app.test_client()
    captured = {}
    recommended = {'num_ctx': 16384, 'temperature': 0.5}

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        return FakeUpstream()

    with patch('requests.post', side_effect=fake_post), \
         patch(
             'app.routes.proxy.compute_fresh_recommended_settings_entry',
             return_value={'settings': recommended, 'source': 'recommended'},
         ):
        resp = client.post('/ollama/api/chat', json={
            'model': 'new-model:latest',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': True,
        })
        resp.get_data()

    assert captured['json']['options']['num_ctx'] == 16384


def test_v1_chat_forwards_vision_images_to_native(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, model_name='vl-test', settings={})
    client = app.test_client()
    captured = {}
    b64 = 'imgdata99'

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        if kwargs.get('stream'):
            class StreamResp:
                status_code = 200
                def iter_lines(self):
                    yield b'{"message":{"role":"assistant","content":"red"},"done":true}'
            return StreamResp()
        raise AssertionError('expected stream')

    with patch('requests.post', side_effect=fake_post), \
         patch('requests.get', return_value=type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'vl-test',
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': 'Color?'},
                    {'type': 'input_image', 'image_url': f'data:image/png;base64,{b64}'},
                ],
            }],
            'stream': True,
        })
        resp.get_data()

    msg = captured['json']['messages'][0]
    assert msg['images'] == [b64]


def test_v1_chat_forwards_tools(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, model_name='tool-test', settings={})
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        if kwargs.get('stream'):
            class StreamResp:
                status_code = 200
                def iter_lines(self):
                    yield b'{"message":{"role":"assistant","content":"ok"},"done":true}'
            return StreamResp()
        raise AssertionError('expected stream')

    tools = [{
        'type': 'function',
        'function': {'name': 'read_file', 'description': 'Read', 'parameters': {'type': 'object'}},
    }]

    with patch('requests.post', side_effect=fake_post), \
         patch('requests.get', return_value=type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'tool-test',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'tools': tools,
            'tool_choice': 'auto',
            'stream': True,
        })
        resp.get_data()

    assert captured['json']['tools'] == tools
    assert captured['json']['tool_choice'] == 'auto'


def test_v1_completions_caps_and_resolves_model(tmp_path, monkeypatch):
    from app.services.v1_model_resolve import invalidate_model_list_cache

    invalidate_model_list_cache()
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch, model_name='qwen3:14b', settings={'num_ctx': 8192})
    client = app.test_client()
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        if kwargs.get('stream'):
            class StreamResp:
                status_code = 200
                def iter_lines(self):
                    yield b'{"response":"ok","done":true}'
            return StreamResp()
        raise AssertionError('expected stream')

    def fake_fetch(_base):
        return ['gemma4:latest', 'qwen3:14b']

    with patch('requests.post', side_effect=fake_post), \
         patch('requests.get', return_value=type('R', (), {'json': lambda s: {'models': []}, 'raise_for_status': lambda s: None})()), \
         patch('app.services.v1_model_resolve._fetch_v1_model_ids', side_effect=fake_fetch):
        resp = client.post('/ollama/v1/completions', json={
            'model': '1',
            'prompt': 'Say hi',
            'stream': True,
            'max_completion_tokens': 99999,
        })
        resp.get_data()

    assert captured['json']['model'] == 'qwen3:14b'
    assert captured['json']['options']['num_predict'] == 16384


def test_api_embed_passthrough(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch)
    client = app.test_client()
    captured = {}

    def fake_request(method, url, **kwargs):
        captured['url'] = url
        captured['data'] = kwargs.get('data')
        return FakeUpstreamResponse()

    with patch('app.routes.proxy._upstream_request', side_effect=fake_request):
        resp = client.post('/ollama/api/embed', data=b'{"model":"m","input":"hi"}', content_type='application/json')

    assert resp.status_code == 200
    assert captured['url'] == 'http://localhost:11434/api/embed'
