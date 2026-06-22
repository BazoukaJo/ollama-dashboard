"""Settings-injecting proxy blueprint for /ollama/api/... and /ollama/v1/... routes.

Native Ollama clients use ``/ollama/api/...``; OpenAI-compatible apps (GPT-style,
Claude Code with Ollama, VS Code extensions, Continue, etc.) use
``/ollama/v1/chat/completions`` and related ``/v1/...`` paths.
Saved per-model settings are merged into inference requests before forwarding.
"""
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Iterator, Optional

import requests
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from app.routes import proxy_upstream as _upstream
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
from app.services.copilot_prewarm import (
    record_model_activity,
    schedule_context_preload,
    touch_keep_alive,
)
from app.services.copilot_proxy import (
    log_copilot_request,
    log_copilot_response,
    log_ollama_proxy_hit,
)
from app.services.error_messages import (
    GENERIC_CONNECTION,
    GENERIC_UPSTREAM,
    log_upstream_error,
)
from app.services.model_settings_helpers import (
    compute_fresh_recommended_settings_entry,
    get_default_settings_template,
    lookup_settings_entry,
    merge_options_for_external_proxy,
)
from app.services.settings_cache import load_settings_file
from app.services.model_residency import pin_keep_alive_for
from app.services.v1_model_resolve import resolve_v1_model_name
from app.services.v1_native_bridge import (
    STREAM_HEARTBEAT,
    StreamRawLine,
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
from app.wsgi_safe import strip_hop_by_hop_headers

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


# Upstream Ollama HTTP timeouts (seconds) — see proxy_upstream for pooled client helpers.
_UPSTREAM_CONNECT_TIMEOUT = _upstream._UPSTREAM_CONNECT_TIMEOUT
_UPSTREAM_STREAM_READ_TIMEOUT = _upstream._UPSTREAM_STREAM_READ_TIMEOUT
_UPSTREAM_STREAM_TIMEOUT = _upstream._UPSTREAM_STREAM_TIMEOUT
_UPSTREAM_INFERENCE_TIMEOUT = _upstream._UPSTREAM_INFERENCE_TIMEOUT
_UPSTREAM_VISION_INFERENCE_TIMEOUT = 300
_UPSTREAM_DEFAULT_TIMEOUT = _upstream._UPSTREAM_DEFAULT_TIMEOUT
_UPSTREAM_PULL_TIMEOUT = 600

_stream_heartbeat_seconds = _upstream.stream_heartbeat_seconds
_stream_first_byte_grace_seconds = _upstream.stream_first_byte_grace_seconds
_stream_first_token_timeout_seconds = _upstream.stream_first_token_timeout_seconds
_stream_stall_timeout_seconds = _upstream.stream_stall_timeout_seconds
_upstream_max_attempts = _upstream.upstream_max_attempts
_upstream_retry_backoff_seconds = _upstream.upstream_retry_backoff_seconds
_copilot_keep_alive = _upstream.copilot_keep_alive
_upstream_post = _upstream.upstream_post
_upstream_post_with_retry = _upstream.upstream_post_with_retry
_upstream_request = _upstream.upstream_request
_filter_upstream_response_headers = _upstream.filter_upstream_response_headers
_ollama_url = _upstream.ollama_url


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
    log_upstream_error(
        logger,
        status_code=upstream.status_code,
        detail=(upstream.text or upstream.reason or 'Upstream error')[:2000],
        context='openai bridge',
    )
    err_text = GENERIC_UPSTREAM
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
    """POST JSON upstream; stream when the client requested streaming.

    Streaming uses the resilient ``_NativeChatStream`` (auto-retry on connect failure, bounded
    first-token / stall timeouts) so native NDJSON clients (incl. VS Code's Ollama provider) get
    the same "never hang, self-heal" guarantees as the OpenAI bridge. Heartbeats are blank
    newlines, which every NDJSON reader skips, so the wire stays valid while the model loads.
    """
    stream = payload.get('stream') if 'stream' in payload else default_stream
    if not stream:
        try:
            response_data = _upstream_post_with_retry(upstream_url, payload, timeout=timeout)
        except requests.RequestException as err:
            logger.warning('Upstream %s connection failed: %s', upstream_url, err)
            body = json.dumps({'error': _ollama_unreachable_text(err)}).encode('utf-8')
            return _native_stream_response(lambda: iter([body]), status=502)
        if response_data.status_code == 200:
            model_name = str(payload.get('model') or '').strip()
            if model_name:
                touch_keep_alive(_ollama_url(), model_name)
        return _proxy_upstream_response(response_data)

    native_stream = _NativeChatStream(
        upstream_url,
        payload,
        heartbeat_seconds=_stream_heartbeat_seconds(),
        timeout=timeout or _UPSTREAM_STREAM_TIMEOUT,
        first_token_timeout=_stream_first_token_timeout_seconds(),
        stall_timeout=_stream_stall_timeout_seconds(),
        max_attempts=_upstream_max_attempts(),
        retry_backoff=_upstream_retry_backoff_seconds(),
        mode='content',
    )
    first_error = native_stream.peek_error(_stream_first_byte_grace_seconds())
    if isinstance(first_error, _UpstreamStatusError):
        err_body = json.dumps({'error': first_error.text}).encode('utf-8')
        return _native_stream_response(lambda: iter([err_body]), status=first_error.status_code)
    if isinstance(first_error, BaseException):
        logger.warning('Upstream %s stream connection failed: %s', upstream_url, first_error)
        err_body = json.dumps({'error': _ollama_unreachable_text(first_error)}).encode('utf-8')
        return _native_stream_response(lambda: iter([err_body]), status=502)

    def stream_body():
        try:
            for chunk in native_stream.iter_raw():
                if chunk is STREAM_HEARTBEAT:
                    yield b'\n'  # NDJSON-safe keep-alive (readers skip blank lines)
                elif chunk:
                    yield chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode('utf-8')
        except _UpstreamStatusError as err:
            yield json.dumps({'error': err.text}).encode('utf-8')
        except Exception as err:  # noqa: BLE001 — surface mid-stream failures, never hang.
            logger.warning('Native stream %s failed mid-flight: %s', upstream_url, err)
            yield json.dumps({'error': _ollama_unreachable_text(err)}).encode('utf-8')

    return _native_stream_response(stream_body)


def _apply_ide_residency_hooks(payload: dict, ollama_url: str) -> None:
    """Prewarm / keep-alive hooks shared by v1 and native proxy paths."""
    model_name = str(payload.get('model') or '').strip()
    if not model_name:
        return
    record_model_activity(model_name)
    if payload.get('keep_alive') is None:
        pinned = pin_keep_alive_for(model_name)
        if pinned is not None:
            payload['keep_alive'] = pinned
        else:
            keep_alive = _copilot_keep_alive()
            if keep_alive is not None:
                payload['keep_alive'] = keep_alive
    entry = _resolve_settings_entry(model_name)
    options = (entry or {}).get('settings') or {}
    if options.get('num_ctx'):
        schedule_context_preload(ollama_url, model_name, dict(options))


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
    _apply_ide_residency_hooks(payload, ollama_url)
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
    log_upstream_error(logger, detail=err, context='ollama connection')
    return GENERIC_CONNECTION


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
    # the per-model reasoning mode (and OLLAMA_COPILOT_ALLOW_THINKING) to take effect.
    think_mode = (pipeline_meta.get('client_extras') or {}).get('copilot_think', 'off')
    apply_copilot_native_defaults(native_payload, payload, think_mode=think_mode)

    log_copilot_request(
        merged_payload,
        path=request.path,
        resolved_model=merged_payload.get('model') or resolved_model or '',
        data_dir=current_app.config.get('DATA_DIR'),
        pipeline={
            **(pipeline_meta or {}),
            'native_think': native_payload.get('think'),
            'copilot_think': think_mode,
        },
    )

    _apply_ide_residency_hooks(native_payload, ollama_url)

    return _forward_v1_chat_via_native(native_payload, merged_payload)


class _ResponseTally:
    """Tally what the proxy actually streamed to the client (for diagnosing empty/lone-token replies)."""

    def __init__(self):
        self.content_chars = 0
        self.reasoning_chars = 0
        self.tool_calls = 0
        self.heartbeats = 0
        self.first_content = ''
        self.finish_reason = None
        self.error: Optional[str] = None

    def observe(self, chunk):
        if not isinstance(chunk, str):
            return
        if chunk.startswith(':'):
            self.heartbeats += 1
            return
        if not chunk.startswith('data:'):
            return
        data = chunk[5:].strip()
        if not data or data == '[DONE]':
            return
        try:
            obj = json.loads(data)
        except (ValueError, TypeError):
            return
        choices = obj.get('choices')
        if not isinstance(choices, list) or not choices:
            return
        choice = choices[0] if isinstance(choices[0], dict) else {}
        raw_delta = choice.get('delta')
        delta = raw_delta if isinstance(raw_delta, dict) else {}
        content = delta.get('content')
        if isinstance(content, str) and content:
            self.content_chars += len(content)
            if len(self.first_content) < 80:
                self.first_content = (self.first_content + content)[:80]
        reasoning = delta.get('reasoning')
        if isinstance(reasoning, str) and reasoning:
            self.reasoning_chars += len(reasoning)
        if delta.get('tool_calls'):
            self.tool_calls += len(delta['tool_calls'])
        if choice.get('finish_reason'):
            self.finish_reason = choice['finish_reason']

    def summary(self, *, agent, think):
        return {
            'agent': bool(agent),
            'think': bool(think),
            'content_chars': self.content_chars,
            'reasoning_chars': self.reasoning_chars,
            'tool_calls': self.tool_calls,
            'heartbeats': self.heartbeats,
            'finish_reason': self.finish_reason,
            'first_content': self.first_content,
            'error': self.error,
        }


class _UpstreamStatusError(Exception):
    """Upstream returned a non-200 status while streaming /api/chat."""

    def __init__(self, status_code, text):
        super().__init__(text)
        self.status_code = status_code
        self.text = text


class _NativeChatStream:
    """Run a blocking streaming upstream POST in a worker thread, resiliently.

    The worker feeds raw items onto a queue; the consumer yields them but emits a
    ``STREAM_HEARTBEAT`` sentinel whenever no item arrives within ``heartbeat_seconds`` so the
    connection to the IDE client stays alive while the model loads. ``peek_error`` lets the
    caller fail fast (proper HTTP status) for an immediate connection/non-200 error before any
    bytes are committed to the client.

    Robustness for an "online provider"-grade local proxy:

    * ``mode='lines'`` reads ``iter_lines()`` (for the OpenAI SSE bridge); ``mode='content'``
      reads ``iter_content()`` (raw byte passthrough for native NDJSON clients).
    * A connection-level failure *before the first byte is produced* is retried automatically
      (up to ``max_attempts``) so a momentarily unreachable / restarting Ollama recovers with no
      user action — the client only sees a few extra keep-alive heartbeats.
    * ``first_token_timeout`` / ``stall_timeout`` bound how long the consumer ever waits, so the
      stream can never hang indefinitely (``None`` disables a bound).
    """

    def __init__(self, url, payload, *, heartbeat_seconds, timeout,
                 first_token_timeout=None, stall_timeout=None,
                 max_attempts=1, retry_backoff=0.4, mode='lines', chunk_size=1024):
        self._queue = queue.Queue()
        self._cancel = threading.Event()
        self._heartbeat_seconds = heartbeat_seconds
        self._first_token_timeout = first_token_timeout
        self._stall_timeout = stall_timeout
        self._pending = None
        self._finished = False
        self._response = None
        self._thread = threading.Thread(
            target=self._worker,
            args=(
                url, payload, timeout,
                max(1, int(max_attempts)), max(0.0, float(retry_backoff)),
                mode, chunk_size,
            ),
            name='copilot-upstream-chat',
            daemon=True,
        )
        self._thread.start()

    def _read_iter(self, upstream, mode, chunk_size):
        if mode == 'content':
            return upstream.iter_content(chunk_size=chunk_size)
        return upstream.iter_lines()

    def _worker(self, url, payload, timeout, max_attempts, retry_backoff, mode, chunk_size):
        produced = False
        attempt = 0
        while not self._cancel.is_set():
            attempt += 1
            upstream = None
            try:
                upstream = _upstream_post(url, payload, stream=True, timeout=timeout)
                self._response = upstream
                if upstream.status_code != 200:
                    text = (upstream.text or upstream.reason or 'Upstream error')[:2000]
                    self._queue.put(('status', upstream.status_code, text))
                    return
                for item in self._read_iter(upstream, mode, chunk_size):
                    if self._cancel.is_set():
                        break
                    produced = True
                    self._queue.put(('line', item, None))
                self._queue.put(('end', None, None))
                return
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
                # Safe to retry only before the client has seen any real bytes (heartbeats only).
                if attempt < max_attempts and not produced and not self._cancel.is_set():
                    if self._cancel.wait(retry_backoff * attempt):
                        return
                    continue
                self._queue.put(('exc', err, None))
                return
            except Exception as err:  # noqa: BLE001 — must always signal, else the consumer hangs.
                self._queue.put(('exc', err, None))
                return
            finally:
                if upstream is not None:
                    try:
                        upstream.close()
                    except Exception:  # noqa: BLE001 — best-effort cleanup.
                        pass

    def close(self):
        """Cancel the worker and unblock any in-flight upstream read (best-effort)."""
        self._cancel.set()
        resp = self._response
        if resp is not None:
            try:
                resp.close()
            except Exception:  # noqa: BLE001 — best-effort.
                pass

    def peek_error(self, grace_seconds):
        """Block up to ``grace_seconds`` for the first item; return an error to fail fast, else None."""
        try:
            item = self._queue.get(timeout=grace_seconds)
        except queue.Empty:
            return None
        kind = item[0]
        if kind == 'status':
            self._finished = True
            return _UpstreamStatusError(item[1], item[2])
        if kind == 'exc':
            self._finished = True
            return item[1]
        self._pending = item
        return None

    def iter_raw(self) -> Iterator[StreamRawLine]:
        """Yield raw items, interleaving STREAM_HEARTBEAT and bounding total/stall wait time."""
        if self._finished:
            return
        start = time.monotonic()
        last_activity = start
        first_seen = False
        try:
            if self._pending is not None:
                item, self._pending = self._pending, None
                if item[0] == 'line':
                    first_seen = True
                    last_activity = time.monotonic()
                    yield item[1]
                elif item[0] == 'end':
                    return
            while True:
                try:
                    kind, first, _second = self._queue.get(timeout=self._heartbeat_seconds)
                except queue.Empty as exc:
                    now = time.monotonic()
                    if (
                        not first_seen
                        and self._first_token_timeout is not None
                        and (now - start) >= self._first_token_timeout
                    ):
                        raise _UpstreamStatusError(
                            504,
                            'Model did not start generating within '
                            f'{int(self._first_token_timeout)}s; aborted to avoid a hang. '
                            'The model may still be loading — please retry.',
                        ) from exc
                    if (
                        first_seen
                        and self._stall_timeout is not None
                        and (now - last_activity) >= self._stall_timeout
                    ):
                        # Mid-stream stall: end gracefully so any partial output is preserved.
                        return
                    yield STREAM_HEARTBEAT
                    continue
                if kind == 'line':
                    first_seen = True
                    last_activity = time.monotonic()
                    yield first
                elif kind == 'end':
                    return
                elif kind == 'status':
                    raise _UpstreamStatusError(first, _second)
                elif kind == 'exc':
                    raise first
        finally:
            self.close()


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
        chat_stream = _NativeChatStream(
            upstream_url,
            native_payload,
            heartbeat_seconds=_stream_heartbeat_seconds(),
            timeout=_UPSTREAM_STREAM_TIMEOUT,
            first_token_timeout=_stream_first_token_timeout_seconds(),
            stall_timeout=_stream_stall_timeout_seconds(),
            max_attempts=_upstream_max_attempts(),
            retry_backoff=_upstream_retry_backoff_seconds(),
        )
        # Fail fast (proper HTTP status) for immediate errors; otherwise commit to the
        # keep-alive stream so a cold model still loading does not look like an empty reply.
        first_error = chat_stream.peek_error(_stream_first_byte_grace_seconds())
        if isinstance(first_error, _UpstreamStatusError):
            return _openai_error_sse(
                first_error.text, status_code=first_error.status_code, model_name=model_name,
            )
        if isinstance(first_error, BaseException):
            logger.warning(
                'Upstream /api/chat stream connection failed (model=%s): %s', model_name, first_error,
            )
            return _openai_error_sse(_ollama_unreachable_text(first_error), model_name=model_name)

        def stream_body():
            opening, cid, created = openai_sse_stream_opening(model_name)
            tally = _ResponseTally()
            yield opening.encode('utf-8')
            try:
                for chunk in stream_native_chat_lines_to_openai_sse(
                    chat_stream.iter_raw(),
                    model=model_name,
                    include_usage=include_usage,
                    completion_id=cid,
                    stream_created=created,
                    omit_reasoning_deltas=not mirror_thinking,
                    mirror_thinking_to_content=mirror_thinking,
                    agent_mode=has_tools,
                    max_stream_chars=proxy_max_response_chars(),
                ):
                    tally.observe(chunk)
                    yield chunk.encode('utf-8')
            except _UpstreamStatusError as err:
                tally.error = f'upstream_status_{err.status_code}'
                for line in openai_error_sse_lines(
                    err.text, status_code=err.status_code, model=model_name, completion_id=cid,
                ):
                    yield line.encode('utf-8')
            except Exception as err:  # noqa: BLE001 — surface any mid-stream failure as SSE, not a hang.
                tally.error = type(err).__name__
                logger.warning(
                    'Upstream /api/chat stream failed mid-flight (model=%s): %s', model_name, err,
                )
                for line in openai_error_sse_lines(
                    _ollama_unreachable_text(err), model=model_name, completion_id=cid,
                ):
                    yield line.encode('utf-8')
            finally:
                log_copilot_response(
                    path=request.path,
                    model=model_name,
                    summary=tally.summary(agent=has_tools, think=think_on),
                    data_dir=current_app.config.get('DATA_DIR'),
                )
                if model_name and tally.error is None:
                    touch_keep_alive(ollama_url, model_name)

        return _sse_response(stream_body)

    try:
        response_data = _upstream_post_with_retry(
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
    if model_name:
        touch_keep_alive(ollama_url, model_name)
    return response


def _forward_v1_via_native_api(native_payload, native_endpoint, _openai_payload):
    """POST to native Ollama API and return an OpenAI-shaped response."""
    ollama_url = _ollama_url()
    upstream_url = f"{ollama_url}{native_endpoint}"
    stream = bool(native_payload.get('stream'))
    model_name = native_payload.get('model') or ''

    if stream:
        gen_stream = _NativeChatStream(
            upstream_url,
            native_payload,
            heartbeat_seconds=_stream_heartbeat_seconds(),
            timeout=_UPSTREAM_STREAM_TIMEOUT,
            first_token_timeout=_stream_first_token_timeout_seconds(),
            stall_timeout=_stream_stall_timeout_seconds(),
            max_attempts=_upstream_max_attempts(),
            retry_backoff=_upstream_retry_backoff_seconds(),
        )
        first_error = gen_stream.peek_error(_stream_first_byte_grace_seconds())
        if isinstance(first_error, _UpstreamStatusError):
            return _openai_error_sse(
                first_error.text, status_code=first_error.status_code, model_name=model_name,
            )
        if isinstance(first_error, BaseException):
            logger.warning(
                'Upstream %s stream connection failed (model=%s): %s',
                native_endpoint, model_name, first_error,
            )
            return _openai_error_sse(_ollama_unreachable_text(first_error), model_name=model_name)

        def stream_body():
            try:
                for chunk in stream_native_generate_lines_to_openai_sse(
                    gen_stream.iter_raw(),
                    model=model_name,
                ):
                    yield chunk.encode('utf-8')
            except _UpstreamStatusError as err:
                for line in openai_error_sse_lines(
                    err.text, status_code=err.status_code, model=model_name,
                ):
                    yield line.encode('utf-8')
            except Exception as err:  # noqa: BLE001 — surface any mid-stream failure as SSE, not a hang.
                logger.warning(
                    'Upstream %s stream failed mid-flight (model=%s): %s',
                    native_endpoint, model_name, err,
                )
                for line in openai_error_sse_lines(
                    _ollama_unreachable_text(err), model=model_name,
                ):
                    yield line.encode('utf-8')

        return _sse_response(stream_body)

    try:
        response_data = _upstream_post_with_retry(upstream_url, native_payload)
    except requests.RequestException as err:
        logger.warning('Upstream %s connection failed (model=%s): %s', native_endpoint, model_name, err)
        return _openai_error_json(_ollama_unreachable_text(err), model_name=model_name)
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
