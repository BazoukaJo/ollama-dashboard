"""Prepare Copilot/v1 chat payloads: settings, prompts, routing, context trim, RAG."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

from app.services.client_payload_compat import cap_num_predict, sanitize_v1_chat_payload
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
            logger.warning('RAG injection failed; continuing without RAG: %s', err)
            meta['rag'] = {'error': str(err)}

    # Normalize multimodal Copilot messages before context trim estimates image-bearing text.
    merged, sanitize_meta = sanitize_v1_chat_payload(merged)
    meta['sanitize'] = sanitize_meta

    trim_enabled = extras.get('context_trim_enabled', True)
    env_trim = os.getenv('CONTEXT_TRIM_ENABLED', 'true').strip().lower()
    if trim_enabled and env_trim not in ('0', 'false', 'no'):
        opts = merged.get('options') if isinstance(merged.get('options'), dict) else {}
        raw_ctx = opts.get('num_ctx')
        try:
            num_ctx = int(raw_ctx) if raw_ctx is not None else 8192
        except (TypeError, ValueError):
            logger.debug('Invalid num_ctx %r; using default 8192 for context trim', raw_ctx)
            num_ctx = 8192
            meta['num_ctx_fallback'] = True
        trimmed_msgs, trim_meta = trim_messages_to_budget(merged.get('messages') or [], num_ctx)
        merged['messages'] = trimmed_msgs
        meta['context_trim'] = trim_meta

    meta['num_ctx'] = (merged.get('options') or {}).get('num_ctx')

    merged, cap_meta = cap_num_predict(
        merged,
        (settings_entry or {}).get('settings') or {},
    )
    meta['client_compat'] = {**sanitize_meta, **cap_meta}
    return merged, meta
