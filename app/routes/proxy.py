"""Settings-injecting proxy blueprint for /ollama/api/... routes.

/ollama/api/chat and /ollama/api/generate requests have the caller's saved
per-model settings merged into their options dict before being forwarded to
the real Ollama API, so external clients (VS Code, ollama run, curl, etc.)
pointed at http://<host>/ollama get the same values the dashboard applies to
its own requests.  All other /ollama/api/... paths pass straight through.

settings_path and ollama_url are resolved at request time from current_app.config
so they automatically pick up any runtime changes to MODEL_SETTINGS_FILE or
OLLAMA_HOST without requiring an app restart.
"""
import json
import logging
from pathlib import Path

import requests
from flask import Blueprint, Response, current_app, request, stream_with_context

from app.services.model_settings_helpers import lookup_settings_entry

logger = logging.getLogger(__name__)

bp = Blueprint('proxy', __name__)


def _ollama_url():
    svc = current_app.config['OLLAMA_SERVICE']
    host, port = svc._get_ollama_host_port()
    return f"http://{host}:{port}"


def _settings_path():
    return Path(current_app.config['MODEL_SETTINGS_FILE'])


@bp.route('/ollama/api/chat', methods=['POST'])
@bp.route('/ollama/api/generate', methods=['POST'])
def intercept_ollama_parameters():
    """Merge saved per-model settings into the request options before forwarding."""
    payload = request.get_json(silent=True) or {}
    model_name = payload.get("model")
    incoming_options = payload.get("options", {})

    dashboard_options = {}
    settings_path = _settings_path()
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                all_settings = json.load(f)
            entry = lookup_settings_entry(all_settings, model_name)
            if entry:
                dashboard_options = entry.get('settings') or {}
        except Exception as proxy_err:
            logger.error("Proxy failed reading settings: %s", proxy_err)

    payload["options"] = {**incoming_options, **dashboard_options}
    ollama_url = _ollama_url()

    def stream_response_tokens():
        upstream = requests.post(
            f"{ollama_url}/api/{request.path.split('/')[-1]}",
            json=payload,
            stream=True
        )
        for chunk in upstream.iter_content(chunk_size=1024):
            if chunk:
                yield chunk

    return Response(stream_with_context(stream_response_tokens()), content_type='application/json')


@bp.route('/ollama/api/<path:catchall>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy_general_ollama_calls(catchall):
    """Pass non-inference calls (tags, show, pull, etc.) straight through to Ollama."""
    if request.method == 'OPTIONS':
        res = Response()
        res.headers['Access-Control-Allow-Origin'] = '*'
        res.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        res.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return res

    forward_headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    ollama_url = _ollama_url()

    response_data = requests.request(
        method=request.method,
        url=f"{ollama_url}/api/{catchall}",
        headers=forward_headers,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False
    )

    proxy_response = Response(
        response_data.content,
        response_data.status_code,
        list(response_data.headers.items())
    )
    proxy_response.headers['Access-Control-Allow-Origin'] = '*'
    return proxy_response
