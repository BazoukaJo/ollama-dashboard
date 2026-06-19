"""Estimate and trim OpenAI/Copilot chat payloads to fit num_ctx budgets."""
from __future__ import annotations

import copy
import json
import os
from typing import Any

_CHARS_PER_TOKEN = 4
_DEFAULT_RESERVE_RATIO = 0.2
_TOKENS_PER_IMAGE = 256
_MAX_TRUNCATION_PASSES = 32
<<<<<<< HEAD
_MIN_LAST_TURN_TOKENS = 512
=======
>>>>>>> f6eb4bf18a980a871f98312bb619c08d6fa148b6
_TRUNCATION_MARKER = '\n\n[... trimmed by ollama-dashboard proxy to fit context window ...]'


def estimate_tokens(text: str) -> int:
    """Fast heuristic token estimate (~4 chars per token for English/code)."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _message_text(message: dict[str, Any]) -> str:
    content = message.get('content')
    if isinstance(content, str) and content.strip():
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


def _chars_for_tokens(tokens: int) -> int:
    return max(0, int(tokens) * _CHARS_PER_TOKEN)


def _truncate_string_to_tokens(text: str, max_tokens: int) -> str:
    """Shrink text to an estimated token budget, keeping head and tail when possible."""
    if not text or max_tokens <= 0:
        return ''
    max_chars = _chars_for_tokens(max_tokens)
    if len(text) <= max_chars:
        return text
    if max_chars <= len(_TRUNCATION_MARKER) + 32:
        return text[:max_chars]
    budget = max_chars - len(_TRUNCATION_MARKER)
    head = max(budget // 6, 64)
    tail = max(budget - head, 64)
    if head + tail > len(text):
        return text[:max_chars]
    return text[:head] + _TRUNCATION_MARKER + text[-tail:]


def _truncate_tool_calls(message: dict[str, Any], token_budget: int) -> None:
    """Drop oldest tool calls until the serialized form fits ``token_budget``."""
    calls = message.get('tool_calls')
    if not isinstance(calls, list) or not calls:
        return
    while len(calls) > 1 and estimate_tokens(json.dumps(calls, ensure_ascii=False)) > token_budget:
        calls.pop(0)
    message['tool_calls'] = calls


def _truncate_message_content(message: dict[str, Any], token_budget: int) -> dict[str, Any]:
    """Return a copy of ``message`` with content shrunk to ``token_budget`` (estimated)."""
    msg = copy.deepcopy(message)
    overhead = 4 + _image_token_cost(msg)
    content_budget = max(1, token_budget - overhead)

    tool_calls = msg.get('tool_calls')
    if isinstance(tool_calls, list) and tool_calls:
        _truncate_tool_calls(msg, content_budget)
        overhead = 4 + _image_token_cost(msg) + estimate_tokens(
            json.dumps(msg.get('tool_calls') or [], ensure_ascii=False),
        )
        content_budget = max(1, token_budget - overhead)

    content = msg.get('content')
    if isinstance(content, str):
        msg['content'] = _truncate_string_to_tokens(content, content_budget)
        return msg

    if isinstance(content, list):
        text_parts: list[str] = []
        non_text: list[Any] = []
        for block in content:
            if isinstance(block, dict):
                btype = str(block.get('type') or '').lower()
                if btype in ('text', 'input_text') and block.get('text'):
                    text_parts.append(str(block['text']))
                elif block.get('text'):
                    text_parts.append(str(block['text']))
                else:
                    non_text.append(block)
            else:
                non_text.append(block)
        joined = '\n'.join(text_parts)
        truncated = _truncate_string_to_tokens(joined, content_budget)
        if non_text:
            msg['content'] = [{'type': 'text', 'text': truncated}] + non_text
        else:
            msg['content'] = truncated
        return msg

    if tool_calls:
        msg.setdefault('content', '')
        return msg

    msg['content'] = ''
    return msg


def _messages_fit(system_msgs: list[dict[str, Any]], rest: list[dict[str, Any]], budget: int) -> bool:
    return estimate_messages_tokens(system_msgs + rest) <= budget


def trim_messages_to_budget(
    messages: list[Any],
    num_ctx: int,
    *,
    strategy: str | None = None,  # noqa: ARG001 — reserved for future strategies
) -> tuple[list[Any], dict[str, Any]]:
    """Trim chat history to fit ``num_ctx``.

    1. Drop oldest non-system messages while more than one remains.
    2. Truncate the remaining message body in-place (never remove the last turn entirely).
    3. If only system messages remain and still exceed budget, truncate system text too.
    """
    msgs = [copy.deepcopy(m) for m in (messages or []) if isinstance(m, dict)]
    budget = completion_budget(num_ctx)
    before = estimate_messages_tokens(msgs)
    meta: dict[str, Any] = {
        'trimmed': False,
        'tokens_before': before,
        'tokens_after': before,
        'budget': budget,
        'messages_removed': 0,
        'content_truncated': 0,
    }
    if before <= budget or not msgs:
        return msgs, meta

    system_msgs = [m for m in msgs if m.get('role') == 'system']
    rest = [m for m in msgs if m.get('role') != 'system']

    # Phase 1: remove oldest non-system messages, but keep at least one.
    while len(rest) > 1 and not _messages_fit(system_msgs, rest, budget):
        rest.pop(0)
        meta['messages_removed'] += 1

<<<<<<< HEAD
    # Phase 2: shrink system prompts before truncating the latest user turn to nothing.
    for _ in range(_MAX_TRUNCATION_PASSES):
        if _messages_fit(system_msgs, rest, budget) or not system_msgs:
            break
        rest_tokens = estimate_messages_tokens(rest)
        sys_allowance = budget - rest_tokens
        if sys_allowance <= 8:
            break
        if estimate_messages_tokens(system_msgs) <= sys_allowance:
            break
        current = system_msgs[0]
        before_msg = estimate_messages_tokens([current])
        target_tokens = max(16, sys_allowance - 4 - _image_token_cost(current))
        truncated = _truncate_message_content(current, target_tokens)
        if estimate_messages_tokens([truncated]) >= before_msg:
            break
        system_msgs[0] = truncated
        meta['content_truncated'] += 1

    # Phase 3: truncate non-system bodies (keep the last user turn usable).
=======
    # Phase 2: truncate non-system bodies (keep the last user turn).
>>>>>>> f6eb4bf18a980a871f98312bb619c08d6fa148b6
    for _ in range(_MAX_TRUNCATION_PASSES):
        if _messages_fit(system_msgs, rest, budget) or not rest:
            break
        overhead_tokens = estimate_messages_tokens(system_msgs)
        remaining = budget - overhead_tokens
        if remaining <= 8:
            break
        current = rest[0]
        before_msg = estimate_messages_tokens([current])
<<<<<<< HEAD
        min_turn = _MIN_LAST_TURN_TOKENS if len(rest) == 1 else 16
        target_tokens = max(min_turn, remaining - 4 - _image_token_cost(current))
=======
        target_tokens = max(16, remaining - 4 - _image_token_cost(current))
>>>>>>> f6eb4bf18a980a871f98312bb619c08d6fa148b6
        truncated = _truncate_message_content(current, target_tokens)
        if estimate_messages_tokens([truncated]) >= before_msg:
            break
        rest[0] = truncated
        meta['content_truncated'] += 1

<<<<<<< HEAD
    # Phase 4: last resort — shrink system again if the user turn still does not fit.
=======
    # Phase 3: shrink system prompts when they leave no room for the user turn.
>>>>>>> f6eb4bf18a980a871f98312bb619c08d6fa148b6
    for _ in range(_MAX_TRUNCATION_PASSES):
        if _messages_fit(system_msgs, rest, budget) or not system_msgs:
            break
        rest_tokens = estimate_messages_tokens(rest)
        sys_allowance = budget - rest_tokens
        if sys_allowance <= 8:
            break
        if estimate_messages_tokens(system_msgs) <= sys_allowance:
            break
        current = system_msgs[0]
        before_msg = estimate_messages_tokens([current])
        target_tokens = max(16, sys_allowance - 4 - _image_token_cost(current))
        truncated = _truncate_message_content(current, target_tokens)
        if estimate_messages_tokens([truncated]) >= before_msg:
            break
        system_msgs[0] = truncated
        meta['content_truncated'] += 1

    trimmed = system_msgs + rest
    after = estimate_messages_tokens(trimmed)
    meta['tokens_after'] = after
    meta['trimmed'] = (
        meta['messages_removed'] > 0
        or meta['content_truncated'] > 0
        or after < before
    )
    if after > budget:
        meta['budget_exceeded'] = True
    return trimmed, meta
