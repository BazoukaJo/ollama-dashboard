"""System prompt presets injected for Copilot/proxy chat when configured."""
from __future__ import annotations

from typing import Any

PRESETS: dict[str, str] = {
    'coding_assistant': (
        'You are a precise coding assistant. Prefer minimal, correct diffs. '
        'Match existing project style. Explain briefly when asked.'
    ),
    'explain_only': (
        'Explain code clearly without rewriting it unless explicitly asked. '
        'Use short examples when helpful.'
    ),
    'test_writer': (
        'Write focused unit tests with clear arrange/act/assert structure. '
        'Cover edge cases; avoid redundant tests.'
    ),
    'reviewer': (
        'Review code for bugs, security issues, and maintainability. '
        'List findings by severity with concrete fix suggestions.'
    ),
}


def resolve_system_prompt(copilot_extras: dict[str, Any] | None) -> str | None:
    """Return system prompt text from copilot extras, or None to skip injection."""
    extras = copilot_extras or {}
    custom = (extras.get('system_prompt_custom') or '').strip()
    if custom:
        return custom
    preset = (extras.get('system_prompt_preset') or '').strip()
    if preset and preset != 'none':
        return PRESETS.get(preset)
    return None


def inject_system_prompt(messages: list[Any], prompt_text: str | None) -> list[Any]:
    """Prepend or merge a system message without duplicating an existing one."""
    if not prompt_text:
        return list(messages or [])
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    for msg in msgs:
        if msg.get('role') == 'system':
            existing = msg.get('content')
            if isinstance(existing, str) and existing.strip():
                merged = f"{prompt_text.strip()}\n\n{existing.strip()}"
                updated = dict(msg)
                updated['content'] = merged
                return [updated if m is msg else m for m in msgs]
            updated = dict(msg)
            updated['content'] = prompt_text
            return [updated if m is msg else m for m in msgs]
    return [{'role': 'system', 'content': prompt_text}, *msgs]
