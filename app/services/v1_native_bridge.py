"""Helpers for OpenAI-compatible /v1 inference via the dashboard proxy.

Ollama's ``/v1/chat/completions`` endpoint does **not** apply ``options.num_ctx`` (verified
on 0.30.x — models load at ~4096 regardless of saved settings). Copilot chat is therefore
**bridged** to native ``/api/chat`` where ``options`` is honored, and responses are converted
back to OpenAI SSE (reasoning, tool calls, finish reasons).

``prepare_v1_chat_completions_payload()`` remains for tests/helpers; production Copilot
traffic uses ``openai_chat_to_native()`` + ``/api/chat``.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Iterator

from app.services.client_payload_compat import (
    estimate_tool_calls_chars,
    normalize_messages_for_ollama,
    proxy_max_response_chars,
    truncate_tool_calls,
)
from app.services.model_settings_helpers import merge_options_for_external_proxy

_OPENAI_OPTION_KEYS = frozenset({
    'temperature', 'top_p', 'top_k', 'seed', 'num_predict', 'num_ctx',
    'repeat_penalty', 'repeat_last_n', 'presence_penalty', 'frequency_penalty',
    'stop', 'min_p', 'typical_p', 'mirostat', 'mirostat_tau', 'mirostat_eta',
    'penalize_newline',
})

# Sentinel a streaming line source can yield while Ollama loads a large model (no bytes flow
# until generation starts). The converter turns it into an SSE *comment* line, which keeps the
# HTTP connection alive for IDE clients (VS Code Copilot, Continue) without injecting any
# `data:` event — OpenAI/SSE parsers ignore lines beginning with ``:``. This is what prevents
# the "Sorry, no response was returned" empty reply when a cold 20GB+ model takes 30-90s to
# produce its first token.
STREAM_HEARTBEAT = object()
_SSE_HEARTBEAT_COMMENT = ': ollama-dashboard keep-alive\n\n'


def _copilot_safe_finish_reason(native: dict[str, Any], *, tool_calls: bool = False) -> str:
    """VS Code Copilot errors on ``finish_reason: length`` — map to ``stop``."""
    reason = native.get('done_reason') or native.get('finish_reason')
    reason_s = reason.strip().lower() if isinstance(reason, str) else ''
    if reason_s == 'length':
        return 'stop'
    if tool_calls or reason_s in ('tool_calls', 'function_call'):
        return 'tool_calls'
    return 'stop'


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


def merge_v1_payload_options(
    payload: dict[str, Any],
    dashboard_settings: dict[str, Any],
) -> dict[str, Any]:
    """Merge saved dashboard settings into a v1 request's effective Ollama options."""
    incoming = _openai_request_options(payload)
    dashboard = {
        k: v for k, v in (dashboard_settings or {}).items()
        if k in _OPENAI_OPTION_KEYS or k == 'num_ctx'
    }
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


def _native_tool_calls_to_openai(native_calls: Any) -> list[dict[str, Any]]:
    """Convert Ollama ``/api/chat`` tool_calls to OpenAI/Copilot SSE shape."""
    if not isinstance(native_calls, list):
        return []
    openai_calls: list[dict[str, Any]] = []
    for i, tc in enumerate(native_calls):
        if not isinstance(tc, dict):
            continue
        raw_fn = tc.get('function')
        fn = raw_fn if isinstance(raw_fn, dict) else {}
        args = fn.get('arguments')
        if isinstance(args, dict):
            args_str = json.dumps(args, ensure_ascii=False)
        elif args is None:
            args_str = '{}'
        else:
            args_str = str(args)
        idx = fn.get('index') if fn.get('index') is not None else i
        openai_calls.append({
            'id': tc.get('id') or f'call_{i}',
            'index': idx,
            'type': tc.get('type') or 'function',
            'function': {
                'name': fn.get('name') or '',
                'arguments': args_str,
            },
        })
    return openai_calls


def _assistant_reasoning_piece(message: dict[str, Any]) -> str | None:
    """Single streaming token of thinking/reasoning from native ``/api/chat``."""
    if not isinstance(message, dict):
        return None
    for key in ('thinking', 'reasoning', 'reasoning_content'):
        piece = message.get(key)
        if piece is not None and str(piece):
            return str(piece)
    return None


def openai_chat_to_native(
    payload: dict[str, Any],
    dashboard_settings: dict[str, Any],
) -> dict[str, Any]:
    """Build ``/api/chat`` JSON from an OpenAI chat-completions body."""
    merged_options = merge_v1_payload_options(payload, dashboard_settings)
    native: dict[str, Any] = {
        'model': payload.get('model'),
        'messages': normalize_messages_for_ollama(payload.get('messages') or []),
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


def apply_copilot_native_defaults(
    native: dict[str, Any],
    openai_payload: dict[str, Any],
    *,
    think_mode: str | None = None,
) -> dict[str, Any]:
    """Tune native ``/api/chat`` thinking for IDE clients (VS Code Copilot, Continue, ...).

    ``think_mode`` (per-model ``copilot_think`` setting) controls reasoning for **plain chat**:

    * ``off`` (default) — force ``think: false`` so Copilot BYOK never shows a lone ``I`` from
      reasoning tokens (it renders ``delta.content`` only).
    * ``auto`` — respect the client's ``reasoning_effort`` (Copilot/OpenAI), else off. The legacy
      ``OLLAMA_COPILOT_ALLOW_THINKING`` env var maps to this so existing setups keep working.
    * ``on`` — force ``think: true`` so capable reasoning models (gemma4, qwen3) actually think;
      the caller mirrors the reasoning into ``delta.content`` so it is visible in Copilot.

    Agent requests (``tools`` present) **always** force ``think: false`` regardless of mode:
    leaving thinking on streams only ``delta.reasoning`` Copilot ignores (users see
    **Sorry, no response was returned**) and risks corrupting the tool-call exchange.
    """
    mode = str(think_mode or 'off').strip().lower()
    env_allow = os.getenv('OLLAMA_COPILOT_ALLOW_THINKING', '').strip().lower() in (
        '1', 'true', 'yes',
    )
    if mode == 'off' and env_allow:
        mode = 'auto'

    if native.get('tools'):
        native['think'] = False
        return native

    if mode == 'on':
        native['think'] = True
    elif mode == 'auto':
        think = _resolve_think_from_openai_payload(openai_payload)
        native['think'] = think if think is not None else False
    else:
        native['think'] = False
    return native


def openai_completion_to_native(
    payload: dict[str, Any],
    dashboard_settings: dict[str, Any],
) -> dict[str, Any]:
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


def openai_sse_stream_opening(
    model: str,
    completion_id: str | None = None,
) -> tuple[str, str, int]:
    """Return an immediate role SSE chunk while Ollama loads the model."""
    cid = completion_id or _completion_id()
    created = _created_ts()
    # Include an empty ``content`` so strict OpenAI SSE parsers (VS Code Copilot BYOK) always
    # see a well-formed first delta even before the model emits its first token.
    line = _openai_chat_chunk(cid, model, {'role': 'assistant', 'content': ''}, created=created)
    return line, cid, created


def native_chat_response_to_openai(
    native: dict[str, Any],
    completion_id: str | None = None,
    *,
    copilot_safe: bool = False,
) -> dict[str, Any]:
    """Convert a non-streaming ``/api/chat`` response to OpenAI chat.completion JSON."""
    cid = completion_id or _completion_id()
    raw_message = native.get('message')
    message = raw_message if isinstance(raw_message, dict) else {}
    content = message.get('content')
    if content is None:
        content = ''
    reasoning = _assistant_reasoning_piece(message)
    content_s = str(content).strip()
    if copilot_safe:
        if not content_s and reasoning:
            content = reasoning
        elif reasoning and len(content_s) <= 3 and len(reasoning.strip()) > len(content_s):
            content = reasoning
    elif not content_s and reasoning:
        content = reasoning
    choice: dict[str, Any] = {
        'index': 0,
        'message': {
            'role': message.get('role') or 'assistant',
            'content': content,
        },
        'finish_reason': _copilot_safe_finish_reason(native),
    }
    if message.get('tool_calls'):
        converted = _native_tool_calls_to_openai(message['tool_calls'])
        if converted:
            choice['message']['tool_calls'] = converted
            choice['finish_reason'] = _copilot_safe_finish_reason(
                native, tool_calls=native.get('done_reason') != 'length',
            )
    if reasoning and not copilot_safe:
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


def native_generate_response_to_openai(
    native: dict[str, Any],
    completion_id: str | None = None,
) -> dict[str, Any]:
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


def _openai_chat_delta_from_native_message(
    msg: dict[str, Any],
    *,
    mirror_thinking_to_content: bool = False,
) -> dict[str, Any]:
    """Build one OpenAI SSE delta from a native ``/api/chat`` message (matches Ollama /v1)."""
    delta: dict[str, Any] = {
        'role': msg.get('role') or 'assistant',
    }
    content = msg.get('content')
    content_s = str(content) if content is not None else ''
    reasoning = _assistant_reasoning_piece(msg)
    if reasoning:
        if mirror_thinking_to_content:
            # Copilot BYOK only renders delta.content; omit reasoning fields it may reject.
            delta['content'] = content_s if content_s.strip() else reasoning
        else:
            delta['reasoning'] = reasoning
            delta['content'] = content_s if content_s.strip() else ''
    elif content is not None:
        delta['content'] = content_s
    else:
        delta['content'] = ''
    if msg.get('tool_calls'):
        converted = _native_tool_calls_to_openai(msg['tool_calls'])
        if converted:
            delta['tool_calls'] = converted
    return delta


def _openai_chat_finish_delta() -> dict[str, Any]:
    """Terminal delta before ``finish_reason`` (matches Ollama /v1)."""
    return {'role': 'assistant', 'content': ''}


def _openai_chat_chunk(
    completion_id: str,
    model: str,
    delta: dict[str, Any],
    *,
    finish_reason: str | None = None,
    usage: dict[str, Any] | None = None,
    created: int | None = None,
) -> str:
    chunk: dict[str, Any] = {
        'id': completion_id,
        'object': 'chat.completion.chunk',
        'created': created if created is not None else _created_ts(),
        'model': model,
        'system_fingerprint': 'fp_ollama',
        'choices': [{
            'index': 0,
            'delta': delta,
            'finish_reason': finish_reason,
        }],
    }
    if usage:
        chunk['usage'] = usage
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _delta_has_substance(delta: dict[str, Any]) -> bool:
    if delta.get('tool_calls'):
        return True
    if delta.get('reasoning'):
        return True
    content = delta.get('content')
    return isinstance(content, str) and content != ''


def _delta_content_char_len(delta: dict[str, Any]) -> int:
    """Length of ``delta.content`` only (used to detect a user-visible answer)."""
    content = delta.get('content')
    return len(str(content)) if isinstance(content, str) else 0


def _delta_outbound_char_len(delta: dict[str, Any]) -> int:
    """Total rendered/streamed payload size for IDE client char budgets."""
    total = _delta_content_char_len(delta)
    reasoning = delta.get('reasoning')
    if isinstance(reasoning, str):
        total += len(reasoning)
    total += estimate_tool_calls_chars(delta.get('tool_calls'))
    return total


def _strip_reasoning_from_delta(delta: dict[str, Any]) -> dict[str, Any]:
    """Copilot BYOK ignores ``delta.reasoning``; omit the field from outbound SSE."""
    out = dict(delta)
    out.pop('reasoning', None)
    return out


def _copilot_content_only_delta(content: str) -> dict[str, Any]:
    """OpenAI-shaped delta with only fields Copilot BYOK renders."""
    return {'role': 'assistant', 'content': content}


# Max content length treated as a thinking bleed prefix (e.g. lone "I") during thinking phase.
_COPILOT_BLEED_MAX_CHARS = 3


def _truncate_delta_for_stream(delta: dict[str, Any], remaining: int) -> dict[str, Any]:
    """Trim delta text and tool_calls so streamed SSE stays under the IDE char budget."""
    if remaining <= 0:
        out = {'role': delta.get('role') or 'assistant', 'content': ''}
        if 'reasoning' in delta:
            out['reasoning'] = ''
        if delta.get('tool_calls'):
            out['tool_calls'] = truncate_tool_calls(delta['tool_calls'], 0)
        return out
    out = dict(delta)
    tool_calls = out.get('tool_calls')
    if isinstance(tool_calls, list) and tool_calls:
        shrunk = truncate_tool_calls(tool_calls, remaining)
        out['tool_calls'] = shrunk
        remaining = max(0, remaining - estimate_tool_calls_chars(shrunk))
    content = out.get('content')
    if isinstance(content, str) and len(content) > remaining:
        out['content'] = content[:remaining]
        remaining = 0
    elif isinstance(content, str):
        remaining -= len(content)
    reasoning = out.get('reasoning')
    if remaining <= 0:
        out.pop('reasoning', None)
    elif isinstance(reasoning, str) and len(reasoning) > remaining:
        out['reasoning'] = reasoning[:remaining]
    return out


def _fit_delta_to_stream_budget(delta: dict[str, Any], remaining: int) -> dict[str, Any]:
    """Return a delta guaranteed to fit the remaining streamed-char budget."""
    if remaining <= 0:
        return _truncate_delta_for_stream(delta, 0)
    if _delta_outbound_char_len(delta) <= remaining:
        return delta
    return _truncate_delta_for_stream(delta, remaining)


def stream_native_chat_lines_to_openai_sse(
    line_iter: Iterator[bytes],
    *,
    model: str,
    completion_id: str | None = None,
    include_usage: bool = False,
    max_stream_chars: int | None = None,
    mirror_thinking_to_content: bool = False,
    omit_reasoning_deltas: bool = False,
    agent_mode: bool = False,
    stream_created: int | None = None,
) -> Iterator[str]:
    """Convert NDJSON ``/api/chat`` stream lines to OpenAI SSE chunks.

    ``mirror_thinking_to_content`` maps native thinking tokens into ``delta.content``
    so IDE clients (VS Code Copilot BYOK) that ignore ``delta.reasoning`` still render output.

    ``omit_reasoning_deltas`` skips streaming ``delta.reasoning`` chunks (Copilot BYOK
    ignores them). Thinking is flushed into ``delta.content`` on ``done`` when needed.

    ``agent_mode`` preserves ``tool_calls`` SSE for Agent clients; thinking is not
    flushed into ``content`` when the model returns tools instead of text.
    """
    cid = completion_id or _completion_id()
    created = stream_created if stream_created is not None else _created_ts()
    seen_tool_calls = False
    yielded_substance = False
    yielded_content = False
    yielded_agent_turn = False
    last_native: dict[str, Any] | None = None
    char_budget = max_stream_chars if max_stream_chars is not None else proxy_max_response_chars()
    streamed_chars = 0
    acc_content: list[str] = []
    acc_thinking: list[str] = []
    in_thinking_phase = False

    for raw in line_iter:
        if raw is STREAM_HEARTBEAT:
            # Keep the IDE client alive while the model loads / prefills a large context.
            # Emit BOTH an SSE comment (helps raw proxies) AND an empty-content data chunk:
            # VS Code Copilot's BYOK parser skips comment lines, so a comment alone does NOT
            # reset its "waiting for the model" timeout. A well-formed empty delta counts as
            # activity (matches Ollama's own ``content: ""`` chunks) and prevents the client
            # from giving up after the first token on slow, CPU-offloaded models.
            yield _SSE_HEARTBEAT_COMMENT
            yield _openai_chat_chunk(
                cid, model, {'role': 'assistant', 'content': ''}, created=created,
            )
            continue
        if not raw:
            continue
        try:
            native = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(native, dict):
            continue
        last_native = native
        raw_msg = native.get('message')
        msg = raw_msg if isinstance(raw_msg, dict) else {}
        reasoning = _assistant_reasoning_piece(msg)
        content_piece = msg.get('content')
        content_s = str(content_piece) if content_piece is not None else ''
        if reasoning:
            acc_thinking.append(reasoning)
            in_thinking_phase = True
        if content_s:
            acc_content.append(content_s)

        delta = _openai_chat_delta_from_native_message(
            msg, mirror_thinking_to_content=mirror_thinking_to_content,
        )
        if delta.get('tool_calls'):
            seen_tool_calls = True
            in_thinking_phase = False
            if omit_reasoning_deltas:
                delta = _strip_reasoning_from_delta(delta)
            if delta.get('content') is None:
                delta['content'] = ''
            # Tool calls are functional payloads for Agent mode: emit them whole and valid against
            # the FULL budget (not just the remaining text budget) so a large-but-legitimate call
            # is never starved by earlier content or dropped — and truncate_tool_calls guarantees
            # the arguments stay valid JSON even in the pathological oversized case.
            if _delta_has_substance(delta):
                out_delta = _fit_delta_to_stream_budget(delta, char_budget)
                if _delta_has_substance(out_delta):
                    yield _openai_chat_chunk(cid, model, out_delta, created=created)
                    yielded_substance = True
                    yielded_agent_turn = True
                    streamed_chars += _delta_outbound_char_len(out_delta)
        elif omit_reasoning_deltas:
            # Copilot BYOK renders delta.content only. Hold thinking tokens and defer
            # short content that arrives during the thinking phase (often a lone "I").
            if content_s and not reasoning:
                joined = ''.join(acc_content).strip()
                is_bleed = (
                    in_thinking_phase
                    and acc_thinking
                    and len(content_s.strip()) <= _COPILOT_BLEED_MAX_CHARS
                    and len(joined) <= _COPILOT_BLEED_MAX_CHARS
                )
                if not is_bleed:
                    in_thinking_phase = False
                    if streamed_chars < char_budget:
                        out_delta = _copilot_content_only_delta(content_s)
                        if streamed_chars + len(content_s) > char_budget:
                            out_delta = _truncate_delta_for_stream(
                                out_delta, char_budget - streamed_chars,
                            )
                        yield _openai_chat_chunk(cid, model, out_delta, created=created)
                        yielded_substance = True
                        if content_s.strip():
                            yielded_content = True
                        streamed_chars += _delta_outbound_char_len(out_delta)
        elif _delta_has_substance(delta) and streamed_chars < char_budget:
            content_len = _delta_outbound_char_len(delta)
            if streamed_chars + content_len > char_budget:
                delta = _truncate_delta_for_stream(delta, char_budget - streamed_chars)
                content_len = _delta_outbound_char_len(delta)
            yield _openai_chat_chunk(cid, model, delta, created=created)
            yielded_substance = True
            if _delta_content_char_len(delta):
                yielded_content = True
            streamed_chars += content_len
        if native.get('done'):
            if not yielded_content and not seen_tool_calls:
                final_text = ''.join(acc_content).strip()
                if (
                    omit_reasoning_deltas
                    and final_text
                    and len(final_text) <= _COPILOT_BLEED_MAX_CHARS
                    and acc_thinking
                ):
                    final_text = ''
                if not final_text and acc_thinking:
                    final_text = ''.join(acc_thinking).strip()
                if final_text and streamed_chars < char_budget:
                    final_delta = _copilot_content_only_delta(
                        final_text[: max(0, char_budget - streamed_chars)],
                    )
                    yield _openai_chat_chunk(cid, model, final_delta, created=created)
                    yielded_substance = True
                    yielded_content = True
            elif seen_tool_calls and not yielded_agent_turn:
                final_delta = _openai_chat_delta_from_native_message(
                    msg, mirror_thinking_to_content=False,
                )
                if omit_reasoning_deltas:
                    final_delta = _strip_reasoning_from_delta(final_delta)
                if final_delta.get('content') is None:
                    final_delta['content'] = ''
                if final_delta.get('tool_calls'):
                    out_delta = _fit_delta_to_stream_budget(final_delta, char_budget)
                    if _delta_has_substance(out_delta):
                        yield _openai_chat_chunk(cid, model, out_delta, created=created)
                        yielded_substance = True
                        yielded_agent_turn = True
                        streamed_chars += _delta_outbound_char_len(out_delta)
            elif not yielded_substance:
                final_delta = _openai_chat_delta_from_native_message(
                    msg, mirror_thinking_to_content=mirror_thinking_to_content or True,
                )
                if _delta_has_substance(final_delta):
                    yield _openai_chat_chunk(cid, model, final_delta, created=created)
                    yielded_substance = True
            finish = _copilot_safe_finish_reason(native, tool_calls=seen_tool_calls)
            usage = None
            if include_usage:
                usage = {}
                if native.get('prompt_eval_count') is not None:
                    usage['prompt_tokens'] = native['prompt_eval_count']
                if native.get('eval_count') is not None:
                    usage['completion_tokens'] = native['eval_count']
                if usage:
                    prompt = usage.get('prompt_tokens', 0)
                    completion = usage.get('completion_tokens', 0)
                    usage['total_tokens'] = prompt + completion
            yield _openai_chat_chunk(
                cid, model, _openai_chat_finish_delta(), finish_reason=finish, usage=usage,
                created=created,
            )

    if last_native is None:
        yield _openai_chat_chunk(cid, model, _openai_chat_finish_delta(), created=created)
        yield _openai_chat_chunk(
            cid, model, _openai_chat_finish_delta(), finish_reason='stop', created=created,
        )
    elif not yielded_substance:
        raw_msg = last_native.get('message')
        msg = raw_msg if isinstance(raw_msg, dict) else {}
        final_delta = _openai_chat_delta_from_native_message(
            msg, mirror_thinking_to_content=mirror_thinking_to_content or True,
        )
        if _delta_has_substance(final_delta):
            yield _openai_chat_chunk(cid, model, final_delta, created=created)
        yield _openai_chat_chunk(
            cid, model, _openai_chat_finish_delta(), finish_reason='stop', created=created,
        )
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
        if raw is STREAM_HEARTBEAT:
            # Comment for raw proxies + an empty-text data chunk so strict clients count it
            # as activity during slow loads (see chat keepalive note above).
            yield _SSE_HEARTBEAT_COMMENT
            yield (
                'data: ' + json.dumps({
                    'id': cid,
                    'object': 'text_completion',
                    'created': _created_ts(),
                    'model': model,
                    'choices': [{'index': 0, 'text': '', 'finish_reason': None}],
                }, ensure_ascii=False) + '\n\n'
            )
            continue
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
