"""Optional task-based model routing for Copilot proxy requests (fast / reasoning / coding)."""
from __future__ import annotations

import re
from typing import Any

_HARD_KEYWORDS = re.compile(
    r'\b(refactor|architect|design|migrate|rewrite|optimize entire|root cause|debug complex)\b',
    re.I,
)

_CODING_KEYWORDS = re.compile(
    r'\b('
    r'implement|write code|fix bug|fix the bug|unit test|pytest|refactor|'
    r'function|class def|typescript|javascript|python|sql query|'
    r'compile error|syntax error|stack trace|pull request|code review|'
    r'debug this|add test|write test|api endpoint|regex'
    r')\b',
    re.I,
)


def _message_text_content(message: dict[str, Any]) -> str:
    """Extract plain text from a message for routing heuristics."""
    content = message.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get('text'):
                    parts.append(str(block['text']))
                elif block.get('type') in ('text', 'input_text') and block.get('text'):
                    parts.append(str(block['text']))
        return '\n'.join(parts)
    return ''


def _last_user_text(messages: list[Any]) -> str:
    for msg in reversed(messages or []):
        if isinstance(msg, dict) and str(msg.get('role') or '').lower() == 'user':
            return _message_text_content(msg)
    if messages and isinstance(messages[-1], dict):
        return _message_text_content(messages[-1])
    return ''


def should_route_to_coding(messages: list[Any]) -> bool:
    """Heuristic: coding-heavy prompts route to the coding tier."""
    text = _last_user_text(messages)
    if not text:
        return False
    if _CODING_KEYWORDS.search(text):
        return True
    if '```' in text and len(text) > 80:
        return True
    return False


def should_route_to_reasoning(messages: list[Any]) -> bool:
    """Heuristic: long or complex prompts may benefit from a reasoning model."""
    text = _last_user_text(messages)
    if not text:
        return False
    if should_route_to_coding(messages):
        return False
    if len(text) > 4000:
        return True
    return bool(_HARD_KEYWORDS.search(text))


def resolve_routed_model(
    payload: dict[str, Any],
    copilot_extras: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    """Return (model_name, route_reason) when routing applies."""
    extras = copilot_extras or {}
    if not extras.get('routing_enabled'):
        return None, None
    fast = (extras.get('routing_fast_model') or '').strip()
    reasoning = (extras.get('routing_reasoning_model') or '').strip()
    coding = (extras.get('routing_coding_model') or '').strip()
    if not fast:
        return None, None
    current = (payload.get('model') or '').strip()
    messages = payload.get('messages') or []

    if coding and should_route_to_coding(messages):
        if current != coding:
            return coding, 'coding_keywords_or_codeblock'
    elif reasoning and should_route_to_reasoning(messages):
        if current != reasoning:
            return reasoning, 'reasoning_keywords_or_length'
    elif current != fast:
        return fast, 'default_fast'
    return None, None
