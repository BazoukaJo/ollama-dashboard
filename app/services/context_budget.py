"""Estimate and trim OpenAI/Copilot chat payloads to fit num_ctx budgets."""
from __future__ import annotations

import json
import os
from typing import Any

_CHARS_PER_TOKEN = 4
_DEFAULT_RESERVE_RATIO = 0.2
_TOKENS_PER_IMAGE = 256


def estimate_tokens(text: str) -> int:
    """Fast heuristic token estimate (~4 chars per token for English/code)."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _message_text(message: dict[str, Any]) -> str:
    content = message.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text' and block.get('text'):
                    parts.append(str(block['text']))
                elif block.get('text'):
                    parts.append(str(block['text']))
        return '\n'.join(parts)
    if message.get('tool_calls'):
        try:
            return json.dumps(message['tool_calls'], ensure_ascii=False)
        except (TypeError, ValueError):
            return str(message['tool_calls'])
    return ''


def _image_token_cost(message: dict[str, Any]) -> int:
    images = message.get('images')
    if isinstance(images, list) and images:
        return len(images) * _TOKENS_PER_IMAGE
    content = message.get('content')
    if isinstance(content, list):
        count = sum(
            1 for block in content
            if isinstance(block, dict)
            and str(block.get('type') or '').lower() in (
                'image', 'image_url', 'input_image',
            )
        )
        return count * _TOKENS_PER_IMAGE
    return 0


def estimate_messages_tokens(messages: list[Any]) -> int:
    total = 0
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        total += 4  # role/overhead
        total += estimate_tokens(_message_text(msg))
        total += _image_token_cost(msg)
    return total


def _reserve_ratio() -> float:
    raw = os.getenv('CONTEXT_RESERVE_RATIO', str(_DEFAULT_RESERVE_RATIO)).strip()
    try:
        ratio = float(raw)
    except ValueError:
        ratio = _DEFAULT_RESERVE_RATIO
    return min(max(ratio, 0.05), 0.5)


def completion_budget(num_ctx: int) -> int:
    """Tokens available for prompt after reserving space for completion."""
    ctx = max(int(num_ctx or 4096), 512)
    return max(256, int(ctx * (1.0 - _reserve_ratio())))


def trim_messages_to_budget(
    messages: list[Any],
    num_ctx: int,
    *,
    strategy: str | None = None,  # noqa: ARG001 — reserved for future strategies
) -> tuple[list[Any], dict[str, Any]]:
    """Trim oldest non-system messages until estimated tokens fit the budget."""
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    budget = completion_budget(num_ctx)
    before = estimate_messages_tokens(msgs)
    meta: dict[str, Any] = {
        'trimmed': False,
        'tokens_before': before,
        'tokens_after': before,
        'budget': budget,
        'messages_removed': 0,
    }
    if before <= budget or not msgs:
        return msgs, meta

    system_msgs = [m for m in msgs if m.get('role') == 'system']
    rest = [m for m in msgs if m.get('role') != 'system']

    while rest and estimate_messages_tokens(system_msgs + rest) > budget:
        rest.pop(0)
        meta['messages_removed'] += 1

    trimmed = system_msgs + rest
    after = estimate_messages_tokens(trimmed)
    meta['tokens_after'] = after
    meta['trimmed'] = meta['messages_removed'] > 0 or after < before
    return trimmed, meta
