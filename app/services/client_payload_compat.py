"""Sanitize and cap external client payloads (VS Code Copilot, Continue, OpenAI SDKs).

Prevents upstream 400s from unsupported OpenAI fields and client-side "Response too long"
errors by capping generation length and stripping parameters Ollama does not accept.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

# VS Code Copilot rejects very large completions client-side; align with dashboard defaults.
_DEFAULT_MAX_PREDICT = 8192
_MAX_PREDICT_CEILING = 16384
_MIN_PREDICT = 64

# Approximate max characters returned to picky IDE clients (reasoning + content + tools).
_DEFAULT_MAX_RESPONSE_CHARS = 96_000

# OpenAI top-level fields safe to forward to Ollama /v1 or native /api/chat.
_ALLOWED_TOP_LEVEL_KEYS = frozenset({
    'model', 'messages', 'prompt', 'suffix', 'stream', 'stream_options', 'options',
    'temperature', 'top_p', 'max_tokens', 'seed', 'stop', 'tools', 'tool_choice',
    'response_format', 'format', 'keep_alive', 'reasoning', 'reasoning_effort', 'effort',
    'think',
})

# Fields clients send that Ollama ignores or may reject — drop before upstream.
_STRIP_TOP_LEVEL_KEYS = frozenset({
    'n', 'logprobs', 'top_logprobs', 'user', 'service_tier', 'parallel_tool_calls',
    'prediction', 'audio', 'modalities', 'metadata', 'store', 'web_search_options',
    'frequency_penalty', 'presence_penalty', 'logit_bias', 'function_call', 'functions',
    'max_completion_tokens',  # mapped to max_tokens, not forwarded as-is
})

_VALID_MESSAGE_ROLES = frozenset({'system', 'user', 'assistant', 'tool'})
_CORS_ALLOW_HEADERS = (
    'Accept, Authorization, Content-Type, OpenAI-Beta, X-Requested-With, '
    'X-Stainless-*, X-OpenAI-*, X-API-Key'
)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def proxy_max_predict() -> int:
    """Max output tokens the proxy allows for external clients."""
    return _env_int(
        'OLLAMA_PROXY_MAX_PREDICT',
        _DEFAULT_MAX_PREDICT,
        minimum=_MIN_PREDICT,
        maximum=_MAX_PREDICT_CEILING,
    )


def proxy_max_response_chars() -> int:
    """Max characters in a non-streaming assistant payload returned to IDE clients."""
    return _env_int(
        'OLLAMA_PROXY_MAX_RESPONSE_CHARS',
        _DEFAULT_MAX_RESPONSE_CHARS,
        minimum=4096,
        maximum=512_000,
    )


def _coerce_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _resolve_requested_max_tokens(payload: dict[str, Any]) -> int | None:
    """Read max output tokens from common OpenAI / Copilot field names."""
    for key in ('max_tokens', 'max_completion_tokens'):
        n = _coerce_positive_int(payload.get(key))
        if n is not None:
            return n
    opts = payload.get('options')
    if isinstance(opts, dict):
        return _coerce_positive_int(opts.get('num_predict'))
    return None


def cap_num_predict(
    payload: dict[str, Any],
    dashboard_settings: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply a safe num_predict / max_tokens ceiling for external clients."""
    hard_ceiling = proxy_max_predict()
    requested = _resolve_requested_max_tokens(payload)
    saved = None
    if isinstance(dashboard_settings, dict):
        saved = _coerce_positive_int(dashboard_settings.get('num_predict'))

    if requested is not None:
        basis = requested
    elif saved is not None:
        basis = saved
    else:
        basis = hard_ceiling

    # Respect dashboard-saved limits above the env default, still bounded for IDE safety.
    upper = min(
        _MAX_PREDICT_CEILING,
        max(hard_ceiling, saved or 0, requested or 0),
    )
    effective = min(basis, upper)
    effective = max(effective, _MIN_PREDICT)
    out = dict(payload)
    opts = dict(out.get('options') or {})
    opts['num_predict'] = effective
    out['options'] = opts
    out['max_tokens'] = effective
    meta = {
        'num_predict_capped': effective,
        'num_predict_requested': requested,
        'num_predict_ceiling': upper,
    }
    return out, meta


_MAX_IMAGES_PER_MESSAGE = 8
_MAX_FETCH_IMAGE_BYTES = 8 * 1024 * 1024


def _fetch_url_as_base64(url: str) -> str | None:
    """Download an image URL (Copilot sometimes sends links instead of inline base64)."""
    if not url or not url.startswith(('http://', 'https://')):
        return None
    try:
        resp = requests.get(url, timeout=20, stream=True)
        resp.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > _MAX_FETCH_IMAGE_BYTES:
                logger.warning('Image URL too large for proxy fetch: %s', url[:120])
                return None
            chunks.append(chunk)
        return base64.b64encode(b''.join(chunks)).decode('ascii')
    except requests.RequestException as err:
        logger.warning('Failed to fetch image URL for Ollama: %s (%s)', url[:120], err)
        return None


def _base64_from_data_url(url: str) -> str | None:
    """Extract raw base64 payload from a data: URL."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if ';base64,' in url:
        return url.split(';base64,', 1)[1].strip() or None
    if url.startswith('data:'):
        return None
    return url


def _image_base64_from_block(block: dict[str, Any]) -> str | None:
    """Pull base64 image bytes from an OpenAI/Copilot content block."""
    block_type = str(block.get('type') or '').lower()
    if block_type in ('image_url', 'input_image'):
        url_obj = block.get('image_url')
        if isinstance(url_obj, dict):
            url = str(url_obj.get('url') or '')
        else:
            url = str(url_obj or block.get('url') or '')
        b64 = _base64_from_data_url(url)
        if b64:
            return b64
        return _fetch_url_as_base64(url)
    if block_type == 'image':
        nested = block.get('image')
        if isinstance(nested, dict):
            for key in ('data', 'b64_json', 'url'):
                val = nested.get(key)
                if isinstance(val, str) and val.strip():
                    b64 = _base64_from_data_url(val)
                    if b64:
                        return b64
                    fetched = _fetch_url_as_base64(val)
                    if fetched:
                        return fetched
        for key in ('image', 'image_url', 'url'):
            val = block.get(key)
            if isinstance(val, str) and val.strip():
                b64 = _base64_from_data_url(val)
                if b64:
                    return b64
                fetched = _fetch_url_as_base64(val)
                if fetched:
                    return fetched
        src = block.get('source')
        if isinstance(src, dict):
            data = src.get('data')
            if data:
                return str(data).strip() or None
            url = src.get('url')
            if url:
                b64 = _base64_from_data_url(str(url))
                if b64:
                    return b64
                return _fetch_url_as_base64(str(url))
        inline = block.get('inline_data')
        if isinstance(inline, dict) and inline.get('data'):
            return str(inline['data']).strip() or None
        for key in ('data', 'b64_json'):
            val = block.get(key)
            if val:
                return str(val).strip() or None
    return None


def _normalize_content_for_ollama(content: Any) -> tuple[str, list[str]]:
    """Convert OpenAI multimodal content to Ollama ``content`` string + ``images`` list."""
    if content is None:
        return '', []
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        return str(content), []

    text_parts: list[str] = []
    images: list[str] = []
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
            continue
        if not isinstance(block, dict):
            text_parts.append(str(block))
            continue
        block_type = str(block.get('type') or '').lower()
        if block_type in ('text', 'input_text'):
            if block.get('text'):
                text_parts.append(str(block['text']))
            continue
        if block.get('text') and block_type not in ('image_url', 'input_image', 'image'):
            text_parts.append(str(block['text']))
            continue
        img_b64 = _image_base64_from_block(block)
        if img_b64:
            if len(images) < _MAX_IMAGES_PER_MESSAGE:
                images.append(img_b64)
            continue
        text = block.get('content') or block.get('input_text')
        if text:
            text_parts.append(str(text))

    text = '\n'.join(text_parts).strip()
    if not text and images:
        text = 'Describe the attached image(s) in detail.'
    return text, images


def _normalize_tool_calls_for_ollama(tool_calls: Any) -> list[dict[str, Any]] | None:
    """Ensure Ollama-native tool_calls (arguments as object when possible)."""
    if not isinstance(tool_calls, list):
        return None
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        item = dict(tc)
        fn = item.get('function')
        if isinstance(fn, dict):
            fn_copy = dict(fn)
            args = fn_copy.get('arguments')
            if isinstance(args, str) and args.strip():
                try:
                    fn_copy['arguments'] = json.loads(args)
                except json.JSONDecodeError:
                    fn_copy['arguments'] = args
            item['function'] = fn_copy
        out.append(item)
    return out or None


def prepare_native_api_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize native ``/api/chat`` bodies from external OpenAI-shaped clients."""
    out = dict(payload or {})
    if 'messages' in out:
        out['messages'] = normalize_messages_for_ollama(out.get('messages') or [])
    return out


def native_api_should_cap_predict() -> bool:
    """IDE paths cap predict by default; native /api/* only when explicitly enabled."""
    return os.getenv('OLLAMA_NATIVE_CAP_PREDICT', 'false').strip().lower() in (
        '1', 'true', 'yes',
    )


def _sanitize_message(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    role = str(message.get('role') or 'user').strip().lower()
    if role == 'developer':
        role = 'system'
    elif role == 'function':
        role = 'tool'
    elif role not in _VALID_MESSAGE_ROLES:
        role = 'user'
    out: dict[str, Any] = {'role': role}
    if 'content' in message:
        text, images = _normalize_content_for_ollama(message.get('content'))
        out['content'] = text
        existing = message.get('images')
        if isinstance(existing, list):
            for item in existing:
                if isinstance(item, str) and item.strip():
                    images.append(item.strip())
        if images:
            out['images'] = images[:_MAX_IMAGES_PER_MESSAGE]
    if message.get('name'):
        out['name'] = str(message['name'])[:128]
    if message.get('tool_calls'):
        normalized = _normalize_tool_calls_for_ollama(message['tool_calls'])
        if normalized:
            out['tool_calls'] = normalized
        if 'content' not in out:
            out['content'] = ''
    if message.get('tool_call_id'):
        out['tool_call_id'] = str(message['tool_call_id'])
    if 'content' not in out and not out.get('tool_calls') and role != 'tool':
        out['content'] = ''
    elif role == 'tool' and 'content' not in out:
        out['content'] = ''
    return out


def normalize_messages_for_ollama(messages: list[Any]) -> list[dict[str, Any]]:
    """Return Ollama-native message dicts (string content + optional images)."""
    out: list[dict[str, Any]] = []
    for msg in messages or []:
        clean = _sanitize_message(msg)
        if clean is not None:
            out.append(clean)
    return out


def messages_have_images(messages: list[Any]) -> bool:
    for msg in messages or []:
        if isinstance(msg, dict) and isinstance(msg.get('images'), list) and msg['images']:
            return True
    return False


def sanitize_v1_chat_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Strip unsupported fields and normalize messages before upstream forward."""
    src = dict(payload or {})
    meta: dict[str, Any] = {'stripped_fields': []}

    # Map newer OpenAI field names before stripping.
    if src.get('max_tokens') is None and src.get('max_completion_tokens') is not None:
        src['max_tokens'] = src['max_completion_tokens']
        meta['mapped_max_completion_tokens'] = True

    stripped = [k for k in src if k in _STRIP_TOP_LEVEL_KEYS]
    if stripped:
        meta['stripped_fields'] = stripped
    out: dict[str, Any] = {k: v for k, v in src.items() if k not in _STRIP_TOP_LEVEL_KEYS}

    out['messages'] = normalize_messages_for_ollama(out.get('messages') or [])

    # Keep only known-safe top-level keys (options/messages already normalized).
    out = {k: v for k, v in out.items() if k in _ALLOWED_TOP_LEVEL_KEYS or k == 'options'}
    if 'stream' not in out:
        out['stream'] = bool(src.get('stream'))

    return out, meta


def prepare_external_v1_payload(
    payload: dict[str, Any],
    dashboard_settings: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Full external-client prep: sanitize then cap output length."""
    sanitized, sanitize_meta = sanitize_v1_chat_payload(payload)
    capped, cap_meta = cap_num_predict(sanitized, dashboard_settings)
    meta = {**sanitize_meta, **cap_meta}
    return capped, meta


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    suffix = '\n\n[truncated by ollama-dashboard proxy — response too long for IDE client]'
    keep = max(0, limit - len(suffix))
    return text[:keep] + suffix


def cap_openai_chat_response(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Truncate oversized non-streaming chat.completion bodies for IDE clients."""
    limit = proxy_max_response_chars()
    meta: dict[str, Any] = {'truncated': False, 'char_limit': limit}
    if not isinstance(body, dict):
        return body, meta

    out = dict(body)
    choices = out.get('choices')
    if not isinstance(choices, list):
        return out, meta

    new_choices = []
    for choice in choices:
        if not isinstance(choice, dict):
            new_choices.append(choice)
            continue
        ch = dict(choice)
        msg = ch.get('message')
        if not isinstance(msg, dict):
            new_choices.append(ch)
            continue
        m = dict(msg)
        total = 0
        for key in ('content', 'reasoning', 'reasoning_content'):
            val = m.get(key)
            if isinstance(val, str) and val:
                total += len(val)
        if total <= limit:
            new_choices.append(ch)
            continue
        meta['truncated'] = True
        remaining = limit
        tool_calls = m.get('tool_calls')
        if isinstance(tool_calls, list):
            try:
                remaining = max(0, remaining - len(json.dumps(tool_calls, ensure_ascii=False)))
            except (TypeError, ValueError) as err:
                logger.debug('Could not estimate tool_calls size for response cap: %s', err)
        for key in ('reasoning', 'reasoning_content', 'content'):
            val = m.get(key)
            if not isinstance(val, str) or not val:
                continue
            if len(val) <= remaining:
                remaining -= len(val)
            else:
                m[key] = _truncate_text(val, remaining)
                remaining = 0
        ch['message'] = m
        new_choices.append(ch)

    out['choices'] = new_choices
    return out, meta
