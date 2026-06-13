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


def test_v1_chat_completions_passthrough_with_num_ctx(tmp_path, monkeypatch):
    """Copilot uses POST /v1/chat/completions; saved num_ctx merges into options."""
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
                def iter_content(self, chunk_size=1024):
                    yield b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
                    yield b'data: [DONE]\n\n'
            return StreamResp()
        class Resp:
            status_code = 200
            content = b'{"choices":[{"message":{"content":"hi"}}]}'
            headers = {'Content-Type': 'application/json'}
        return Resp()

    with patch('requests.post', side_effect=fake_post):
        resp = client.post('/ollama/v1/chat/completions', json={
            'model': 'copilot-test',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': True,
        })
        resp.get_data()

    assert resp.status_code == 200
    assert captured['url'] == 'http://localhost:11434/v1/chat/completions'
    assert captured['json']['options']['temperature'] == 0.55
    assert captured['json']['options']['num_ctx'] == 16384
    assert captured['json']['messages'] == [{'role': 'user', 'content': 'hi'}]


def test_v1_chat_stream_upstream_error_returns_sse(tmp_path, monkeypatch):
    app = _create_app_for_proxy_tests(tmp_path, monkeypatch)
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
