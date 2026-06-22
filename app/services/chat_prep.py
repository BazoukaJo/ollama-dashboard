"""Shared Ask? chat message preparation for /api/chat and /api/chat/agent."""
from __future__ import annotations

from typing import Any

from app.services.ask_attachments import AttachmentError, prepare_chat_from_attachments


def normalize_ask_messages(messages: Any) -> list[dict[str, Any]]:
    """Keep only user/assistant/system turns with string content for Ask? multi-turn chat."""
    if not isinstance(messages, list):
        return []
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get('role')
        if role not in ('user', 'assistant', 'system'):
            continue
        content = msg.get('content')
        if content is None:
            continue
        entry: dict[str, Any] = {'role': role, 'content': str(content)}
        images = msg.get('images')
        if role == 'user' and isinstance(images, list) and images:
            entry['images'] = images
        out.append(entry)
    return out


def model_has_vision(model_info: dict[str, Any] | None) -> bool:
    if not model_info:
        return False
    has_vision = model_info.get('has_vision')
    if has_vision is not None:
        return bool(has_vision)
    caps = model_info.get('capabilities')
    if isinstance(caps, list):
        caps_lower = {str(c).lower() for c in caps}
        return bool(caps_lower & {'vision', 'image', 'multimodal'})
    return False


def model_has_reasoning(model_info: dict[str, Any] | None) -> bool:
    if not model_info:
        return False
    if model_info.get('has_reasoning') is True:
        return True
    caps = model_info.get('capabilities')
    if isinstance(caps, list):
        caps_lower = {str(c).lower() for c in caps}
        return bool(caps_lower & {'thinking', 'reasoning', 'think'})
    return False


def model_has_tools(model_info: dict[str, Any] | None) -> bool:
    if not model_info:
        return False
    if model_info.get('has_tools') is True:
        return True
    if model_info.get('has_tools') is False:
        return False
    caps = model_info.get('capabilities')
    if isinstance(caps, list):
        caps_lower = {str(c).lower() for c in caps}
        return bool(caps_lower & {'tools', 'tool', 'tool_use', 'function_calling'})
    return False


def prepare_ask_chat_messages(
    data: dict[str, Any],
    model_info: dict[str, Any],
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None, int | None]:
    """Build messages from an Ask? POST body.

    Returns ``(messages, None, None)`` on success or ``(None, error_body, status)`` on failure.
    """
    prompt = data.get('prompt')
    attachments = data.get('attachments')
    raw_messages = data.get('messages')
    vision = model_has_vision(model_info)

    messages = normalize_ask_messages(raw_messages)
    if messages:
        if messages[-1].get('role') != 'user':
            return None, {'error': 'The last message must be from the user'}, 400
        if attachments:
            try:
                prepared = prepare_chat_from_attachments(
                    messages[-1].get('content') or '',
                    attachments,
                    model_has_vision=vision,
                )
            except AttachmentError as exc:
                return None, {'error': str(exc)}, 400
            messages[-1]['content'] = prepared['prompt']
            if prepared.get('images'):
                messages[-1]['images'] = prepared['images']
        return messages, None, None

    if not (prompt or '').strip() and not attachments:
        return None, {'error': 'Enter a question or add an attachment'}, 400
    try:
        prepared = prepare_chat_from_attachments(
            prompt or '',
            attachments,
            model_has_vision=vision,
        )
    except AttachmentError as exc:
        return None, {'error': str(exc)}, 400
    user_message: dict[str, Any] = {'role': 'user', 'content': prepared['prompt']}
    if prepared.get('images'):
        user_message['images'] = prepared['images']
    return [user_message], None, None
