"""Prepare Copilot/v1 chat payloads: settings, prompts, routing, context trim, RAG."""
from __future__ import annotations

import os
from typing import Any

from app.services.context_budget import trim_messages_to_budget
from app.services.copilot_extras import get_client_extras
from app.services.model_router import resolve_routed_model
from app.services.system_prompts import inject_system_prompt, resolve_system_prompt
from app.services.v1_native_bridge import prepare_v1_chat_completions_payload


def prepare_copilot_payload(
    payload: dict[str, Any],
    settings_entry: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (merged_payload, pipeline_meta) for upstream forward."""
    merged = prepare_v1_chat_completions_payload(
        payload,
        (settings_entry or {}).get('settings') or {},
    )
    extras = get_client_extras(settings_entry)
    meta: dict[str, Any] = {'client_extras': extras}

    routed, reason = resolve_routed_model(merged, extras)
    if routed:
        merged['model'] = routed
        meta['routed_model'] = routed
        meta['route_reason'] = reason

    prompt = resolve_system_prompt(extras)
    if prompt:
        merged['messages'] = inject_system_prompt(merged.get('messages') or [], prompt)
        meta['system_prompt_injected'] = True

    if extras.get('rag_enabled') and os.getenv('RAG_ENABLED', '').strip().lower() in ('1', 'true', 'yes'):
        try:
            from app.services.rag import inject_rag_context
            merged['messages'], rag_meta = inject_rag_context(merged.get('messages') or [])
            meta['rag'] = rag_meta
        except Exception as err:  # pylint: disable=broad-exception-caught
            meta['rag'] = {'error': str(err)}

    trim_enabled = extras.get('context_trim_enabled', True)
    env_trim = os.getenv('CONTEXT_TRIM_ENABLED', 'true').strip().lower()
    if trim_enabled and env_trim not in ('0', 'false', 'no'):
        num_ctx = int((merged.get('options') or {}).get('num_ctx') or 8192)
        trimmed_msgs, trim_meta = trim_messages_to_budget(merged.get('messages') or [], num_ctx)
        if trim_meta.get('trimmed'):
            merged['messages'] = trimmed_msgs
        meta['context_trim'] = trim_meta

    meta['num_ctx'] = (merged.get('options') or {}).get('num_ctx')
    return merged, meta
