"""Per-client proxy options stored alongside per-model Ollama settings.

Saved under the ``client`` key in ``model_settings.json``. Legacy ``copilot`` entries
are still read for backward compatibility.
"""
from __future__ import annotations

from typing import Any

# How the proxy treats model "thinking"/reasoning for IDE clients (VS Code Copilot, etc.):
#   off  -> force think:false (clean, fast answers; safe default that never shows a lone "I")
#   auto -> respect the client's reasoning_effort (Copilot/OpenAI), else off
#   on   -> force think:true for plain chat and mirror the reasoning into the visible answer
# Agent/tool turns always run with think:false regardless of this setting, so the tool
# exchange is never corrupted by reasoning tokens.
COPILOT_THINK_MODES = ('off', 'auto', 'on')

DEFAULT_CLIENT_EXTRAS: dict[str, Any] = {
    'system_prompt_preset': 'none',
    'system_prompt_custom': '',
    'context_trim_enabled': True,
    'copilot_think': 'off',
    'routing_enabled': False,
    'routing_fast_model': '',
    'routing_reasoning_model': '',
    'rag_enabled': False,
}

# Backward-compatible alias
DEFAULT_COPILOT_EXTRAS = DEFAULT_CLIENT_EXTRAS


def normalize_client_extras(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_CLIENT_EXTRAS)
    if not isinstance(raw, dict):
        return out
    for key in DEFAULT_CLIENT_EXTRAS:
        if key in raw:
            out[key] = raw[key]
    if isinstance(out.get('system_prompt_custom'), str):
        out['system_prompt_custom'] = out['system_prompt_custom'].strip()[:8000]
    out['context_trim_enabled'] = bool(out.get('context_trim_enabled'))
    out['copilot_think'] = _normalize_think_mode(out.get('copilot_think'))
    out['routing_enabled'] = bool(out.get('routing_enabled'))
    out['rag_enabled'] = bool(out.get('rag_enabled'))
    return out


def _normalize_think_mode(value: Any) -> str:
    """Coerce a saved/posted reasoning mode to a known value (default ``off``)."""
    text = str(value or 'off').strip().lower()
    if text in ('1', 'true', 'yes', 'enable', 'enabled'):
        return 'on'
    if text in ('0', 'false', 'no', 'disable', 'disabled', 'none'):
        return 'off'
    return text if text in COPILOT_THINK_MODES else 'off'


normalize_copilot_extras = normalize_client_extras


def get_client_extras(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return dict(DEFAULT_CLIENT_EXTRAS)
    raw = entry.get('client')
    if raw is None:
        raw = entry.get('copilot')  # legacy
    return normalize_client_extras(raw)


get_copilot_extras = get_client_extras


def attach_client_to_api_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of a settings entry with a normalized ``client`` block for API/UI."""
    if not isinstance(entry, dict):
        return {'settings': {}, 'client': dict(DEFAULT_CLIENT_EXTRAS)}
    out = dict(entry)
    out['client'] = get_client_extras(entry)
    return out
