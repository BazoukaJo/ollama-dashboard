"""Optional task-based model routing for Copilot proxy requests."""
from __future__ import annotations

import re
from typing import Any

_HARD_KEYWORDS = re.compile(
    r'\b(refactor|architect|design|migrate|rewrite|optimize entire|root cause|debug complex)\b',
    re.I,
)


def should_route_to_reasoning(messages: list[Any]) -> bool:
    """Heuristic: long or complex prompts may benefit from a reasoning model."""
    if not messages:
        return False
    last = messages[-1] if isinstance(messages[-1], dict) else {}
    text = last.get('content')
    if not isinstance(text, str):
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
    if not fast or not reasoning:
        return None, None
    current = (payload.get('model') or '').strip()
    messages = payload.get('messages') or []
    if should_route_to_reasoning(messages):
        if current != reasoning:
            return reasoning, 'reasoning_keywords_or_length'
    elif current != fast:
        return fast, 'default_fast'
    return None, None
