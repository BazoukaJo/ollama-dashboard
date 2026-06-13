"""Per-client proxy options stored alongside per-model Ollama settings.

Saved under the ``client`` key in ``model_settings.json``. Legacy ``copilot`` entries
are still read for backward compatibility.
"""
from __future__ import annotations

from typing import Any

DEFAULT_CLIENT_EXTRAS: dict[str, Any] = {
    'system_prompt_preset': 'none',
    'system_prompt_custom': '',
    'context_trim_enabled': True,
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
    out['routing_enabled'] = bool(out.get('routing_enabled'))
    out['rag_enabled'] = bool(out.get('rag_enabled'))
    return out


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
