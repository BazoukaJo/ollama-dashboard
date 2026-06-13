"""Helpers for OpenAI-compatible /v1 inference via the dashboard proxy.

``prepare_v1_chat_completions_payload()`` merges saved dashboard settings into the
``options`` dict on Copilot / OpenAI chat requests before passthrough to Ollama
``/v1/chat/completions``.

``/v1/completions`` is still translated to native ``/api/generate`` (where ``options`` is
always honored).  Stream/response conversion helpers remain for that path and for tests.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Iterator

from app.services.model_settings_helpers import merge_options_for_external_proxy

_OPENAI_OPTION_KEYS = frozenset({
    'temperature', 'top_p', 'top_k', 'seed', 'num_predict', 'num_ctx',
    'repeat_penalty', 'repeat_last_n', 'presence_penalty', 'frequency_penalty',
    'stop', 'min_p', 'typical_p', 'mirostat', 'mirostat_tau', 'mirostat_eta',
    'penalize_newline',
})


def _openai_request_options(payload: dict[str, Any]) -> dict[str, Any]:
    """Map standard OpenAI top-level fields into Ollama ``options``."""
    opts: dict[str, Any] = {}
    if isinstance(payload.get('options'), dict):
        opts.update(payload['options'])
    if payload.get('temperature') is not None:
        opts['temperature'] = payload['temperature']
    if payload.get('top_p') is not None:
        opts['top_p'] = payload['top_p']
    if payload.get('max_tokens') is not None:
        opts['num_predict'] = payload['max_tokens']
    if payload.get('seed') is not None:
        opts['seed'] = payload['seed']
    stop = payload.get('stop')
    if stop is not None:
        opts['stop'] = stop
    return opts


def merge_v1_payload_options(payload: dict[str, Any], dashboard_settings: dict[str, Any]) -> dict[str, Any]:
    """Merge saved dashboard settings into a v1 request's effective Ollama options."""
    incoming = _openai_request_options(payload)
    dashboard = {k: v for k, v in (dashboard_settings or {}).items() if k in _OPENAI_OPTION_KEYS or k == 'num_ctx'}
    return merge_options_for_external_proxy(incoming, dashboard)


def prepare_v1_chat_completions_payload(
    payload: dict[str, Any],
    dashboard_settings: dict[str, Any],
) -> dict[str, Any]:
    """OpenAI-shaped body for Ollama ``/v1/chat/completions`` with merged ``options``."""
    merged = dict(payload or {})
    merged['options'] = merge_v1_payload_options(payload, dashboard_settings)
    return merged


def _resolve_think_from_openai_payload(payload: dict[str, Any]) -> Any | None:
    """Map OpenAI/Copilot reasoning fields to Ollama ``think`` (unset = model default)."""
    effort = None
    reasoning = payload.get('reasoning')
    if isinstance(reasoning, dict):
        effort = reasoning.get('effort')
    effort = payload.get('reasoning_effort') or payload.get('effort') or effort
    if effort is None:
        return None
    effort_s = str(effort).strip().lower()
    if effort_s in ('none', 'false', 'off', '0'):
        return False
    return effort


def _assistant_reasoning_piece(message: dict[str, Any]) -> str | None:
    """Single streaming token of thinking/reasoning from native ``/api/chat``."""
    if not isinstance(message, dict):
        return None
    for key in ('thinking', 'reasoning', 'reasoning_content'):
        piece = message.get(key)
        if piece is not None and str(piece):
            return str(piece)
    return None


def openai_chat_to_native(payload: dict[str, Any], dashboard_settings: dict[str, Any]) -> dict[str, Any]:
    """Build ``/api/chat`` JSON from an OpenAI chat-completions body."""
    merged_options = merge_v1_payload_options(payload, dashboard_settings)
    native: dict[str, Any] = {
        'model': payload.get('model'),
        'messages': payload.get('messages') or [],
        'stream': bool(payload.get('stream')),
        'options': merged_options,
    }
    if payload.get('tools'):
        native['tools'] = payload['tools']
    if payload.get('tool_choice') is not None:
        native['tool_choice'] = payload['tool_choice']
    think = _resolve_think_from_openai_payload(payload)
    if think is not None:
        native['think'] = think
    if payload.get('keep_alive') is not None:
        native['keep_alive'] = payload['keep_alive']
    rf = payload.get('response_format')
    if isinstance(rf, dict):
        rf_type = str(rf.get('type') or '').lower()
        if rf_type == 'json_object':
            native['format'] = 'json'
        elif rf_type == 'json_schema' and isinstance(rf.get('json_schema'), dict):
            schema = rf['json_schema'].get('schema')
            if schema is not None:
                native['format'] = schema
    elif payload.get('format') is not None:
        native['format'] = payload['format']
    return native


def openai_completion_to_native(payload: dict[str, Any], dashboard_settings: dict[str, Any]) -> dict[str, Any]:
    """Build ``/api/generate`` JSON from an OpenAI completions body."""
    merged_options = merge_v1_payload_options(payload, dashboard_settings)
    native: dict[str, Any] = {
        'model': payload.get('model'),
        'prompt': payload.get('prompt', ''),
        'stream': bool(payload.get('stream')),
        'options': merged_options,
    }
    if payload.get('suffix') is not None:
        native['suffix'] = payload['suffix']
    if payload.get('keep_alive') is not None:
        native['keep_alive'] = payload['keep_alive']
    return native


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _created_ts() -> int:
    return int(time.time())


def native_chat_response_to_openai(native: dict[str, Any], completion_id: str | None = None) -> dict[str, Any]:
    """Convert a non-streaming ``/api/chat`` response to OpenAI chat.completion JSON."""
    cid = completion_id or _completion_id()
    message = native.get('message') if isinstance(native.get('message'), dict) else {}
    content = message.get('content')
    if content is None:
        content = ''
    choice: dict[str, Any] = {
        'index': 0,
        'message': {
            'role': message.get('role') or 'assistant',
            'content': content,
        },
        'finish_reason': 'stop' if native.get('done', True) else None,
    }
    if message.get('tool_calls'):
        choice['message']['tool_calls'] = message['tool_calls']
        choice['finish_reason'] = 'tool_calls'
    reasoning = _assistant_reasoning_piece(message)
    if reasoning:
        choice['message']['reasoning'] = reasoning
    usage = {}
    if native.get('prompt_eval_count') is not None:
        usage['prompt_tokens'] = native['prompt_eval_count']
    if native.get('eval_count') is not None:
        usage['completion_tokens'] = native['eval_count']
    if usage:
        usage['total_tokens'] = usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0)
    return {
        'id': cid,
        'object': 'chat.completion',
        'created': _created_ts(),
        'model': native.get('model') or '',
        'choices': [choice],
        'usage': usage or None,
    }


def native_generate_response_to_openai(native: dict[str, Any], completion_id: str | None = None) -> dict[str, Any]:
    """Convert a non-streaming ``/api/generate`` response to OpenAI completion JSON."""
    cid = completion_id or _completion_id()
    return {
        'id': cid,
        'object': 'text_completion',
        'created': _created_ts(),
        'model': native.get('model') or '',
        'choices': [{
            'index': 0,
            'text': native.get('response') or '',
            'finish_reason': 'stop' if native.get('done', True) else None,
        }],
    }


def _openai_chat_chunk(
    completion_id: str,
    model: str,
    delta: dict[str, Any],
    *,
    finish_reason: str | None = None,
    usage: dict[str, Any] | None = None,
) -> str:
    chunk: dict[str, Any] = {
        'id': completion_id,
        'object': 'chat.completion.chunk',
        'created': _created_ts(),
        'model': model,
        'choices': [{
            'index': 0,
            'delta': delta,
            'finish_reason': finish_reason,
        }],
    }
    if usage:
        chunk['usage'] = usage
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def stream_native_chat_lines_to_openai_sse(
    line_iter: Iterator[bytes],
    *,
    model: str,
    completion_id: str | None = None,
    include_usage: bool = False,
) -> Iterator[str]:
    """Convert NDJSON ``/api/chat`` stream lines to OpenAI SSE chunks."""
    cid = completion_id or _completion_id()
    sent_role = False
    last_native: dict[str, Any] | None = None

    for raw in line_iter:
        if not raw:
            continue
        try:
            native = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(native, dict):
            continue
        last_native = native
        msg = native.get('message') if isinstance(native.get('message'), dict) else {}
        delta: dict[str, Any] = {}
        if not sent_role:
            delta['role'] = msg.get('role') or 'assistant'
            sent_role = True
        content = msg.get('content')
        reasoning = _assistant_reasoning_piece(msg)
        if reasoning:
            # Match Ollama /v1: reasoning tokens with empty content until answer text.
            delta['reasoning'] = reasoning
            delta['reasoning_content'] = reasoning
            if not content:
                delta['content'] = ''
        elif content:
            delta['content'] = content
        if msg.get('tool_calls'):
            delta['tool_calls'] = msg['tool_calls']
        if delta:
            yield _openai_chat_chunk(cid, model, delta)
        if native.get('done'):
            finish = 'tool_calls' if msg.get('tool_calls') else 'stop'
            usage = None
            if include_usage:
                usage = {}
                if native.get('prompt_eval_count') is not None:
                    usage['prompt_tokens'] = native['prompt_eval_count']
                if native.get('eval_count') is not None:
                    usage['completion_tokens'] = native['eval_count']
                if usage:
                    usage['total_tokens'] = usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0)
            yield _openai_chat_chunk(cid, model, {}, finish_reason=finish, usage=usage)

    if last_native is None:
        yield _openai_chat_chunk(cid, model, {'role': 'assistant', 'content': ''})
        yield _openai_chat_chunk(cid, model, {}, finish_reason='stop')
    yield 'data: [DONE]\n\n'


def stream_native_generate_lines_to_openai_sse(
    line_iter: Iterator[bytes],
    *,
    model: str,
    completion_id: str | None = None,
) -> Iterator[str]:
    """Convert NDJSON ``/api/generate`` stream lines to OpenAI text completion SSE."""
    cid = completion_id or _completion_id()
    for raw in line_iter:
        if not raw:
            continue
        try:
            native = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(native, dict):
            continue
        text = native.get('response')
        if text:
            chunk = {
                'id': cid,
                'object': 'text_completion',
                'created': _created_ts(),
                'model': model,
                'choices': [{'index': 0, 'text': text, 'finish_reason': None}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        if native.get('done'):
            chunk = {
                'id': cid,
                'object': 'text_completion',
                'created': _created_ts(),
                'model': model,
                'choices': [{'index': 0, 'text': '', 'finish_reason': 'stop'}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield 'data: [DONE]\n\n'
            return
    yield 'data: [DONE]\n\n'


def openai_error_sse_lines(
    message: str,
    *,
    status_code: int = 502,
    model: str = '',
) -> Iterator[str]:
    """SSE error chunks for OpenAI-compatible streaming clients (Copilot, etc.)."""
    payload: dict[str, Any] = {
        'error': {
            'message': message,
            'type': 'upstream_error',
            'code': status_code,
        },
    }
    if model:
        payload['model'] = model
    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    yield 'data: [DONE]\n\n'
