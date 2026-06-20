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

from app.services.client_payload_compat import (
    _CORS_ALLOW_HEADERS,
    cap_num_predict,
    cap_openai_chat_response,
    messages_have_images,
    native_api_should_cap_predict,
    prepare_native_api_payload,
    proxy_max_response_chars,
    sanitize_v1_chat_payload,
)
from app.services.copilot_pipeline import prepare_copilot_payload
from app.services.copilot_prewarm import record_model_activity
from app.services.copilot_proxy import log_copilot_request, log_ollama_proxy_hit
from app.services.model_settings_helpers import (
    compute_fresh_recommended_settings_entry,
    get_default_settings_template,
    lookup_settings_entry,
    merge_options_for_external_proxy,
)
from app.services.settings_cache import load_settings_file
from app.services.v1_model_resolve import resolve_v1_model_name
from app.services.v1_native_bridge import (
    apply_copilot_native_defaults,
    merge_v1_payload_options,
    native_chat_response_to_openai,
    native_generate_response_to_openai,
    openai_chat_to_native,
    openai_completion_to_native,
    openai_error_sse_lines,
    openai_sse_stream_opening,
    prepare_v1_chat_completions_payload,
    stream_native_chat_lines_to_openai_sse,
    stream_native_generate_lines_to_openai_sse,
)
from app.wsgi_safe import HOP_BY_HOP_HEADERS, strip_hop_by_hop_headers

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


# Upstream Ollama HTTP timeouts (seconds).
_UPSTREAM_CONNECT_TIMEOUT = 30
_UPSTREAM_STREAM_READ_TIMEOUT = 3600
_UPSTREAM_STREAM_TIMEOUT = (_UPSTREAM_CONNECT_TIMEOUT, _UPSTREAM_STREAM_READ_TIMEOUT)
_UPSTREAM_INFERENCE_TIMEOUT = 120
_UPSTREAM_VISION_INFERENCE_TIMEOUT = 300
_UPSTREAM_DEFAULT_TIMEOUT = 30
_UPSTREAM_PULL_TIMEOUT = 600


def _upstream_post(url, payload, *, stream=False, timeout=None):
    """POST JSON to Ollama; always passes an explicit timeout."""
    if timeout is None:
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
        if key.lower() in HOP_BY_HOP_HEADERS:
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
    res.headers['Access-Control-Allow-Headers'] = _CORS_ALLOW_HEADERS
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


def _resolve_settings_entry(model_name):
    """Match dashboard Ask: recommended defaults when no saved entry exists."""
    entry = _load_settings_entry(model_name)
    if entry is not None:
        return entry
    if not model_name:
        return None
    try:
        svc = current_app.config['OLLAMA_SERVICE']
        return compute_fresh_recommended_settings_entry(svc, model_name)
    except (AttributeError, TypeError, RuntimeError, OSError, json.JSONDecodeError) as proxy_err:
        logger.warning('Proxy settings fallback for %s failed: %s', model_name, proxy_err)
        return {
            'settings': get_default_settings_template(),
            'source': 'default',
        }


def _openai_error_response(upstream, model_name=''):
    """OpenAI-shaped JSON error for non-streaming Copilot clients."""
    err_text = (upstream.text or upstream.reason or 'Upstream error')[:2000]
    body: dict = {
        'error': {
            'message': err_text,
            'type': 'upstream_error',
            'code': upstream.status_code,
        },
    }
    if model_name:
        body['model'] = model_name
    response = Response(
        json.dumps(body),
        status=upstream.status_code,
        content_type='application/json',
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


def _proxy_upstream_response(response_data):
    proxy_response = Response(
        response_data.content,
        response_data.status_code,
        _filter_upstream_response_headers(response_data.headers),
    )
    proxy_response.headers['Access-Control-Allow-Origin'] = '*'
    return proxy_response


def _native_stream_response(stream_body, *, status=200):
    response = Response(
        stream_with_context(stream_body()),
        status=status,
        content_type='application/json',
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'no-cache, no-transform'
    return response


def _forward_json_post_with_settings(upstream_url, payload, *, default_stream=False, timeout=None):
    """POST JSON upstream; stream when the client requested streaming."""
    stream = payload.get('stream') if 'stream' in payload else default_stream
    if stream:
        upstream = _upstream_post(upstream_url, payload, stream=True, timeout=timeout)
        if upstream.status_code != 200:
            err_body = upstream.content or json.dumps(
                {'error': upstream.text or upstream.reason or 'Upstream error'},
            ).encode('utf-8')

            def err_body_iter():
                yield err_body

            return _native_stream_response(err_body_iter, status=upstream.status_code)

        def stream_body():
            for chunk in upstream.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk

        return _native_stream_response(stream_body)

    response_data = _upstream_post(upstream_url, payload, timeout=timeout)
    return _proxy_upstream_response(response_data)


def _merge_saved_settings_into_payload(payload):
    model_name = payload.get("model")
    incoming_options = payload.get("options", {})
    entry = _resolve_settings_entry(model_name)
    dashboard_options = (entry or {}).get('settings') or {}
    payload["options"] = merge_options_for_external_proxy(
        incoming_options, dashboard_options
    )
    return payload


def _prepare_native_inference_payload(raw_payload, endpoint):
    """Settings merge + optional multimodal normalize + vision timeout for native API."""
    payload = _merge_saved_settings_into_payload(dict(raw_payload or {}))
    settings = (payload.get('options') or {})
    if endpoint == 'chat':
        payload = prepare_native_api_payload(payload)
        if native_api_should_cap_predict():
            payload, _meta = cap_num_predict(payload, settings)
    elif native_api_should_cap_predict():
        payload, _meta = cap_num_predict(payload, settings)

    has_images = endpoint == 'chat' and messages_have_images(payload.get('messages') or [])
    timeout = (
        _UPSTREAM_VISION_INFERENCE_TIMEOUT
        if has_images and not payload.get('stream', True)
        else None
    )
    return payload, timeout


@bp.route('/ollama/api/chat', methods=['POST', 'OPTIONS'])
@bp.route('/ollama/api/generate', methods=['POST', 'OPTIONS'])
def intercept_ollama_parameters():
    """Merge saved per-model settings into native Ollama API requests."""
    if request.method == 'OPTIONS':
        return _cors_preflight_response('POST, OPTIONS')

    endpoint = request.path.rsplit('/', 1)[-1]
    payload, infer_timeout = _prepare_native_inference_payload(
        request.get_json(silent=True) or {}, endpoint,
    )
    ollama_url = _ollama_url()
    return _forward_json_post_with_settings(
        f"{ollama_url}/api/{endpoint}",
        payload,
        default_stream=True,
        timeout=infer_timeout,
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
    return strip_hop_by_hop_headers(response)


def _ollama_unreachable_text(err):
    return (
        f'Cannot reach Ollama at {_ollama_url()}: {err}. '
        'Start the Ollama service (the dashboard header can do this) and retry.'
    )


def _openai_error_json(message, *, status_code=502, model_name=''):
    """OpenAI-shaped JSON error for non-streaming clients."""
    body: dict = {'error': {'message': message[:2000], 'type': 'upstream_error', 'code': status_code}}
    if model_name:
        body['model'] = model_name
    response = Response(json.dumps(body), status=status_code, content_type='application/json')
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


def _openai_error_sse(message, *, status_code=502, model_name=''):
    """OpenAI-shaped SSE error stream for streaming clients (VS Code Copilot, etc.)."""
    def error_stream():
        for line in openai_error_sse_lines(message[:2000], status_code=status_code, model=model_name):
            yield line.encode('utf-8')

    return _sse_response(error_stream, status=status_code)


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

    settings_entry = _resolve_settings_entry(payload.get('model'))
    settings_dict = (settings_entry or {}).get('settings') or {}

    use_passthrough = os.getenv('OLLAMA_V1_PASSTHROUGH', 'false').strip().lower() in ('1', 'true', 'yes')
    if use_passthrough:
        passthrough_payload = prepare_v1_chat_completions_payload(payload, settings_dict)
        passthrough_payload, _sanitize_meta = sanitize_v1_chat_payload(passthrough_payload)
        passthrough_payload, _cap_meta = cap_num_predict(passthrough_payload, settings_dict)
        logger.warning(
            'OLLAMA_V1_PASSTHROUGH enabled: v1 chat bypasses Copilot SSE hardening '
            '(delta.reasoning may reach clients). Use default bridge for VS Code Copilot.',
        )
        return _forward_v1_chat_passthrough(passthrough_payload)

    merged_payload, pipeline_meta = prepare_copilot_payload(payload, settings_entry)

    native_payload = openai_chat_to_native(merged_payload, {})
    # Resolve thinking from the ORIGINAL request: prepare_copilot_payload() sanitizes away
    # reasoning/effort/think, so apply_copilot_native_defaults must see the raw payload for
    # OLLAMA_COPILOT_ALLOW_THINKING to actually take effect (otherwise the toggle is dead).
    apply_copilot_native_defaults(native_payload, payload)

    log_copilot_request(
        merged_payload,
        path=request.path,
        resolved_model=merged_payload.get('model') or resolved_model or '',
        data_dir=current_app.config.get('DATA_DIR'),
        pipeline={**(pipeline_meta or {}), 'native_think': native_payload.get('think')},
    )

    model_for_preload = merged_payload.get('model') or ''
    if model_for_preload:
        record_model_activity(model_for_preload)

    return _forward_v1_chat_via_native(native_payload, merged_payload)


def _forward_v1_chat_via_native(native_payload, openai_payload):
    """POST to native ``/api/chat`` and return an OpenAI-shaped response."""
    ollama_url = _ollama_url()
    upstream_url = f"{ollama_url}/api/chat"
    stream = bool(native_payload.get('stream'))
    model_name = native_payload.get('model') or ''
    include_usage = _v1_include_usage(openai_payload)
    has_images = messages_have_images(native_payload.get('messages') or [])
    has_tools = bool(native_payload.get('tools'))
    # When thinking is explicitly enabled for this request, surface it to VS Code Copilot
    # (which renders delta.content only) by mirroring reasoning into content — but never for
    # agent/tool turns, where mixing thinking into content would corrupt the tool exchange.
    think_val = native_payload.get('think')
    think_on = think_val is not None and think_val is not False
    mirror_thinking = think_on and not has_tools
    infer_timeout = (
        _UPSTREAM_VISION_INFERENCE_TIMEOUT if has_images else _UPSTREAM_INFERENCE_TIMEOUT
    )

    if stream:
        try:
            upstream = _upstream_post(upstream_url, native_payload, stream=True)
        except requests.RequestException as err:
            logger.warning('Upstream /api/chat stream connection failed (model=%s): %s', model_name, err)
            return _openai_error_sse(_ollama_unreachable_text(err), model_name=model_name)
        if upstream.status_code != 200:
            err_text = (upstream.text or upstream.reason or 'Upstream error')[:2000]
            return _openai_error_sse(err_text, status_code=upstream.status_code, model_name=model_name)

        def stream_body():
            opening, cid, created = openai_sse_stream_opening(model_name)
            yield opening.encode('utf-8')
            for chunk in stream_native_chat_lines_to_openai_sse(
                upstream.iter_lines(),
                model=model_name,
                include_usage=include_usage,
                completion_id=cid,
                stream_created=created,
                omit_reasoning_deltas=not mirror_thinking,
                mirror_thinking_to_content=mirror_thinking,
                agent_mode=has_tools,
                max_stream_chars=proxy_max_response_chars(),
            ):
                yield chunk.encode('utf-8')

        return _sse_response(stream_body)

    try:
        response_data = _upstream_post(
            upstream_url, native_payload, timeout=infer_timeout,
        )
    except requests.RequestException as err:
        logger.warning('Upstream /api/chat connection failed (model=%s): %s', model_name, err)
        return _openai_error_json(_ollama_unreachable_text(err), model_name=model_name)
    if response_data.status_code != 200:
        return _openai_error_response(response_data, model_name)
    try:
        native_body = response_data.json()
    except ValueError as err:
        logger.warning(
            'Upstream /api/chat returned non-JSON body (status=%s, model=%s): %s',
            response_data.status_code, model_name, err,
        )
        return _proxy_upstream_response(response_data)
    openai_body = native_chat_response_to_openai(
        native_body,
        copilot_safe=not bool(native_payload.get('tools')),
    )
    openai_body, _trunc_meta = cap_openai_chat_response(openai_body)
    response = Response(
        json.dumps(openai_body),
        status=200,
        content_type='application/json',
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


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
        return _openai_error_response(response_data, model_name)
    try:
        native_body = response_data.json()
    except ValueError as err:
        logger.warning(
            'Upstream %s returned non-JSON body (status=%s, model=%s): %s',
            native_endpoint, response_data.status_code, model_name, err,
        )
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


@bp.route('/ollama/v1/completions', methods=['POST', 'OPTIONS'])
def intercept_v1_completions():
    """OpenAI completions: route via native /api/generate so num_ctx applies."""
    if request.method == 'OPTIONS':
        return _cors_preflight_response('POST, OPTIONS')

    payload = dict(request.get_json(silent=True) or {})
    ollama_url = _ollama_url()
    resolved_model = resolve_v1_model_name(ollama_url, payload.get('model'))
    if resolved_model:
        payload['model'] = resolved_model

    if payload.get('max_tokens') is None and payload.get('max_completion_tokens') is not None:
        payload['max_tokens'] = payload['max_completion_tokens']

    settings_entry = _resolve_settings_entry(payload.get('model'))
    settings_dict = (settings_entry or {}).get('settings') or {}
    merged = dict(payload)
    merged['options'] = merge_v1_payload_options(payload, settings_dict)
    merged, _meta = cap_num_predict(merged, settings_dict)
    native_payload = openai_completion_to_native(merged, {})
    return _forward_v1_via_native_api(native_payload, '/api/generate', merged)


@bp.route('/ollama/api/<path:catchall>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy_general_ollama_calls(catchall):
    """Pass non-inference calls (tags, show, pull, etc.) straight through to Ollama."""
    if request.method == 'OPTIONS':
        return _cors_preflight_response()

    forward_headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    ollama_url = _ollama_url()

    timeout = _UPSTREAM_PULL_TIMEOUT if catchall == 'pull' else _UPSTREAM_DEFAULT_TIMEOUT
    try:
        response_data = _upstream_request(
            request.method,
            f"{ollama_url}/api/{catchall}",
            headers=forward_headers,
            data=request.get_data(),
            cookies=request.cookies,
            timeout=timeout,
        )
    except requests.RequestException as err:
        logger.warning('Upstream /api/%s connection failed: %s', catchall, err)
        return _openai_error_json(_ollama_unreachable_text(err))

    return _proxy_upstream_response(response_data)


@bp.route('/ollama/v1/<path:catchall>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy_v1_openai_calls(catchall):
    """Pass OpenAI-compatible routes (models list, etc.) through to Ollama /v1/..."""
    if request.method == 'OPTIONS':
        return _cors_preflight_response()

    forward_headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    ollama_url = _ollama_url()

    try:
        response_data = _upstream_request(
            request.method,
            f"{ollama_url}/v1/{catchall}",
            headers=forward_headers,
            data=request.get_data(),
            cookies=request.cookies,
        )
    except requests.RequestException as err:
        logger.warning('Upstream /v1/%s connection failed: %s', catchall, err)
        return _openai_error_json(_ollama_unreachable_text(err))

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
