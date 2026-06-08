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
    assert options['num_ctx'] == 16384
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
