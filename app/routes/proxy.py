"""Settings-injecting proxy blueprint for /ollama/api/... and /ollama/v1/... routes.

Native Ollama clients use ``/ollama/api/...``; OpenAI-compatible apps (GPT-style,
Claude Code with Ollama, VS Code extensions, Continue, etc.) use
``/ollama/v1/chat/completions`` and related ``/v1/...`` paths.
Saved per-model settings are merged into inference requests before forwarding.
"""
import json
import logging
import os
from pathlib import Path

import requests
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from app.services.copilot_pipeline import prepare_copilot_payload
from app.services.copilot_prewarm import record_model_activity, schedule_context_preload, touch_keep_alive
from app.services.copilot_proxy import log_copilot_request, log_ollama_proxy_hit
from app.services.model_settings_helpers import (
    lookup_settings_entry,
    merge_options_for_external_proxy,
)
from app.services.settings_cache import load_settings_file
from app.services.v1_model_resolve import resolve_v1_model_name
from app.services.v1_native_bridge import (
    native_generate_response_to_openai,
    openai_completion_to_native,
    openai_error_sse_lines,
    stream_native_generate_lines_to_openai_sse,
)

logger = logging.getLogger(__name__)

bp = Blueprint('proxy', __name__)


@bp.before_request
def _log_incoming_ollama_request():
    """Record every /ollama hit so we can tell if VS Code is using the dashboard."""
    if request.path.endswith('/copilot-debug') or request.path.endswith('/proxy-debug'):
        return
    log_ollama_proxy_hit(
        method=request.method,
        path=request.path,
        data_dir=current_app.config.get('DATA_DIR'),
        extra={'query': request.query_string.decode('utf-8', errors='replace')[:120] or None},
    )


# Waitress (and PEP 3333) reject hop-by-hop headers on WSGI responses. Ollama often
# sends Transfer-Encoding / Connection; forwarding them causes 500 Internal Server Error.
_HOP_BY_HOP_HEADERS = frozenset({
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade',
})

# Upstream Ollama HTTP timeouts (seconds).
_UPSTREAM_CONNECT_TIMEOUT = 30
_UPSTREAM_STREAM_READ_TIMEOUT = 3600
_UPSTREAM_STREAM_TIMEOUT = (_UPSTREAM_CONNECT_TIMEOUT, _UPSTREAM_STREAM_READ_TIMEOUT)
_UPSTREAM_INFERENCE_TIMEOUT = 120
_UPSTREAM_DEFAULT_TIMEOUT = 30
_UPSTREAM_PULL_TIMEOUT = 600


def _upstream_post(url, payload, *, stream=False):
    """POST JSON to Ollama; always passes an explicit timeout."""
    timeout = _UPSTREAM_STREAM_TIMEOUT if stream else _UPSTREAM_INFERENCE_TIMEOUT
    return requests.post(url, json=payload, stream=stream, timeout=timeout)


def _upstream_request(method, url, **kwargs):
    """Forward an arbitrary HTTP method to Ollama; always passes an explicit timeout."""
    timeout = kwargs.pop('timeout', _UPSTREAM_DEFAULT_TIMEOUT)
    return requests.request(
        method=method,
        url=url,
        allow_redirects=False,
        timeout=timeout,
        **kwargs,
    )


def _filter_upstream_response_headers(headers):
    """Return header pairs safe to pass through a WSGI Response."""
    safe = []
    for key, value in headers.items():
        if key.lower() in _HOP_BY_HOP_HEADERS:
            continue
        if key.lower() == 'content-encoding':
            continue
        safe.append((key, value))
    return safe


def _ollama_url():
    svc = current_app.config['OLLAMA_SERVICE']
    host, port = svc.get_ollama_host_port()
    return f"http://{host}:{port}"


def _settings_path():
    return Path(current_app.config['MODEL_SETTINGS_FILE'])


def _cors_preflight_response(methods='GET, POST, PUT, DELETE, OPTIONS'):
    res = Response()
    res.headers['Access-Control-Allow-Origin'] = '*'
    res.headers['Access-Control-Allow-Methods'] = methods
    res.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return res


def _load_dashboard_options(model_name):
    dashboard_options = {}
    settings_path = _settings_path()
    if not model_name:
        return dashboard_options
    try:
        all_settings = load_settings_file(settings_path)
        entry = lookup_settings_entry(all_settings, model_name)
        if entry:
            dashboard_options = entry.get('settings') or {}
    except (OSError, json.JSONDecodeError) as proxy_err:
        logger.error("Proxy failed reading settings: %s", proxy_err)
    return dashboard_options


def _load_settings_entry(model_name):
    settings_path = _settings_path()
    if not model_name:
        return None
    try:
        all_settings = load_settings_file(settings_path)
        return lookup_settings_entry(all_settings, model_name)
    except (OSError, json.JSONDecodeError) as proxy_err:
        logger.error("Proxy failed reading settings entry: %s", proxy_err)
        return None


def _proxy_upstream_response(response_data):
    proxy_response = Response(
        response_data.content,
        response_data.status_code,
        _filter_upstream_response_headers(response_data.headers),
    )
    proxy_response.headers['Access-Control-Allow-Origin'] = '*'
    return proxy_response


def _forward_json_post_with_settings(upstream_url, payload, default_stream=False):
    """POST JSON upstream; stream when the client requested streaming."""
    stream = payload.get('stream') if 'stream' in payload else default_stream
    if stream:
        def stream_body():
            upstream = _upstream_post(upstream_url, payload, stream=True)
            for chunk in upstream.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk

        return Response(stream_with_context(stream_body()), content_type='application/json')

    response_data = _upstream_post(upstream_url, payload)
    return _proxy_upstream_response(response_data)


def _merge_saved_settings_into_payload(payload):
    model_name = payload.get("model")
    incoming_options = payload.get("options", {})
    dashboard_options = _load_dashboard_options(model_name)
    payload["options"] = merge_options_for_external_proxy(
        incoming_options, dashboard_options
    )
    return payload


@bp.route('/ollama/api/chat', methods=['POST'])
@bp.route('/ollama/api/generate', methods=['POST'])
def intercept_ollama_parameters():
    """Merge saved per-model settings into native Ollama API requests."""
    payload = _merge_saved_settings_into_payload(request.get_json(silent=True) or {})
    ollama_url = _ollama_url()
    endpoint = request.path.rsplit('/', 1)[-1]
    return _forward_json_post_with_settings(
        f"{ollama_url}/api/{endpoint}", payload, default_stream=True
    )


def _v1_include_usage(payload):
    stream_opts = payload.get('stream_options')
    return isinstance(stream_opts, dict) and bool(stream_opts.get('include_usage'))


def _sse_response(stream_body, *, status=200):
    response = Response(
        stream_with_context(stream_body()),
        status=status,
        content_type='text/event-stream; charset=utf-8',
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'no-cache, no-transform'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


def _forward_v1_chat_passthrough(payload):
    """Forward Copilot chat to Ollama native ``/v1/chat/completions`` (byte passthrough)."""
    ollama_url = _ollama_url()
    upstream_url = f"{ollama_url}/v1/chat/completions"
    stream = bool(payload.get('stream'))
    model_name = payload.get('model') or ''

    if stream:
        upstream = _upstream_post(upstream_url, payload, stream=True)
        if upstream.status_code != 200:
            err_text = (upstream.text or upstream.reason or 'Upstream error')[:2000]

            def error_stream():
                for line in openai_error_sse_lines(
                    err_text, status_code=upstream.status_code, model=model_name,
                ):
                    yield line.encode('utf-8')

            return _sse_response(error_stream, status=upstream.status_code)

        def stream_body():
            for chunk in upstream.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk

        return _sse_response(stream_body)

    response_data = _upstream_post(upstream_url, payload)
    return _proxy_upstream_response(response_data)


def _handle_v1_chat_completions():
    """Shared handler for OpenAI-compatible chat completion requests."""
    if request.method == 'OPTIONS':
        return _cors_preflight_response('POST, OPTIONS')

    payload = dict(request.get_json(silent=True) or {})
    if 'stream' not in payload:
        accept = request.headers.get('Accept', '')
        if 'text/event-stream' in accept:
            payload['stream'] = True

    ollama_url = _ollama_url()
    raw_model = payload.get('model')
    resolved_model = resolve_v1_model_name(ollama_url, raw_model)
    if resolved_model:
        payload['model'] = resolved_model

    settings_entry = _load_settings_entry(payload.get('model'))
    merged_payload, pipeline_meta = prepare_copilot_payload(payload, settings_entry)

    log_copilot_request(
        merged_payload,
        path=request.path,
        resolved_model=merged_payload.get('model') or resolved_model or '',
        data_dir=current_app.config.get('DATA_DIR'),
        pipeline=pipeline_meta,
    )

    model_for_preload = merged_payload.get('model') or ''
    options = merged_payload.get('options') or {}
    if os.getenv('OLLAMA_COPILOT_PRELOAD_CTX', 'true').strip().lower() in ('1', 'true', 'yes'):
        schedule_context_preload(ollama_url, model_for_preload, options)
    if model_for_preload:
        record_model_activity(model_for_preload)
        touch_keep_alive(ollama_url, model_for_preload)

    return _forward_v1_chat_passthrough(merged_payload)


def _forward_v1_via_native_api(native_payload, native_endpoint, _openai_payload):
    """POST to native Ollama API and return an OpenAI-shaped response."""
    ollama_url = _ollama_url()
    upstream_url = f"{ollama_url}{native_endpoint}"
    stream = bool(native_payload.get('stream'))
    model_name = native_payload.get('model') or ''

    if stream:
        upstream = _upstream_post(upstream_url, native_payload, stream=True)
        if upstream.status_code != 200:
            err_text = (upstream.text or upstream.reason or 'Upstream error')[:2000]

            def error_stream():
                for line in openai_error_sse_lines(
                    err_text, status_code=upstream.status_code, model=model_name,
                ):
                    yield line.encode('utf-8')

            response = Response(
                stream_with_context(error_stream()),
                status=upstream.status_code,
                content_type='text/event-stream; charset=utf-8',
            )
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Cache-Control'] = 'no-cache, no-transform'
            response.headers['X-Accel-Buffering'] = 'no'
            return response

        def stream_body():
            for chunk in stream_native_generate_lines_to_openai_sse(
                upstream.iter_lines(),
                model=model_name,
            ):
                yield chunk.encode('utf-8')

        return _sse_response(stream_body)

    response_data = _upstream_post(upstream_url, native_payload)
    if response_data.status_code != 200:
        return _proxy_upstream_response(response_data)
    try:
        native_body = response_data.json()
    except ValueError:
        return _proxy_upstream_response(response_data)
    openai_body = native_generate_response_to_openai(native_body)
    response = Response(
        json.dumps(openai_body),
        status=200,
        content_type='application/json',
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@bp.route('/ollama/v1/chat/completions', methods=['POST', 'OPTIONS'])
@bp.route('/ollama/chat/completions', methods=['POST', 'OPTIONS'])
def intercept_v1_chat_completions():
    """OpenAI-compatible chat: settings merge, context trim, native /v1 passthrough."""
    return _handle_v1_chat_completions()


@bp.route('/ollama/v1/completions', methods=['POST'])
def intercept_v1_completions():
    """OpenAI completions: route via native /api/generate so num_ctx applies."""
    payload = request.get_json(silent=True) or {}
    dashboard_options = _load_dashboard_options(payload.get('model'))
    native_payload = openai_completion_to_native(payload, dashboard_options)
    return _forward_v1_via_native_api(native_payload, '/api/generate', payload)


@bp.route('/ollama/api/<path:catchall>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy_general_ollama_calls(catchall):
    """Pass non-inference calls (tags, show, pull, etc.) straight through to Ollama."""
    if request.method == 'OPTIONS':
        return _cors_preflight_response()

    forward_headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    ollama_url = _ollama_url()

    timeout = _UPSTREAM_PULL_TIMEOUT if catchall == 'pull' else _UPSTREAM_DEFAULT_TIMEOUT
    response_data = _upstream_request(
        request.method,
        f"{ollama_url}/api/{catchall}",
        headers=forward_headers,
        data=request.get_data(),
        cookies=request.cookies,
        timeout=timeout,
    )

    return _proxy_upstream_response(response_data)


@bp.route('/ollama/v1/<path:catchall>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy_v1_openai_calls(catchall):
    """Pass OpenAI-compatible routes (models list, etc.) through to Ollama /v1/..."""
    if request.method == 'OPTIONS':
        return _cors_preflight_response()

    forward_headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    ollama_url = _ollama_url()

    response_data = _upstream_request(
        request.method,
        f"{ollama_url}/v1/{catchall}",
        headers=forward_headers,
        data=request.get_data(),
        cookies=request.cookies,
    )

    return _proxy_upstream_response(response_data)


@bp.route('/ollama/proxy-debug', methods=['GET'])
@bp.route('/ollama/copilot-debug', methods=['GET'])  # legacy
def proxy_debug_log():
    """Return recent API proxy log lines (local troubleshooting)."""
    log_file = Path(current_app.config.get('DATA_DIR', '.')) / 'copilot_proxy.log'
    if not log_file.is_file():
        return jsonify({'lines': [], 'message': 'No external client requests logged yet.'})
    try:
        text = log_file.read_text(encoding='utf-8')
        lines = [ln for ln in text.strip().splitlines() if ln.strip()]
        return jsonify({'lines': lines[-20:], 'log_path': str(log_file.resolve())})
    except OSError as err:
        return jsonify({'error': str(err)}), 500


@bp.route('/ollama', methods=['GET', 'OPTIONS'])
def proxy_ollama_root():
    """Health check for clients that probe the configured base URL (e.g. VS Code)."""
    if request.method == 'OPTIONS':
        return _cors_preflight_response('GET, OPTIONS')
    return jsonify({
        'success': True,
        'message': (
            'Ollama dashboard API proxy — OpenAI-compatible: /ollama/v1/chat/completions; '
            'native Ollama: /ollama/api/tags or /ollama/v1/models'
        ),
        'ollama_api_base': request.host_url.rstrip('/') + '/ollama',
    })
