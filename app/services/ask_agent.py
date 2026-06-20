"""Ask? agent mode — server-side Ollama /api/chat tool loop using MCP tool registry."""
from __future__ import annotations

import json
import os
from typing import Any, Iterator

import requests

from app.services.client_payload_compat import normalize_messages_for_ollama
from app.services.mcp_tools import execute_tool, get_tool_definitions
from app.services.v1_native_bridge import apply_copilot_native_defaults


def _max_iterations() -> int:
    try:
        return max(1, min(int(os.getenv('ASK_AGENT_MAX_ITERATIONS', '8')), 20))
    except (TypeError, ValueError):
        return 8


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_tool_calls(calls: Any) -> list[dict[str, Any]]:
    if not isinstance(calls, list):
        return []
    out: list[dict[str, Any]] = []
    for i, tc in enumerate(calls):
        if not isinstance(tc, dict):
            continue
        fn = tc.get('function') if isinstance(tc.get('function'), dict) else {}
        name = str(fn.get('name') or '').strip()
        if not name:
            continue
        args = _parse_tool_arguments(fn.get('arguments'))
        out.append({
            'id': tc.get('id') or f'call_{i}',
            'type': tc.get('type') or 'function',
            'function': {'name': name, 'arguments': args},
        })
    return out


def _stream_chat_turn(
    session,
    chat_url: str,
    payload: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Run one streamed /api/chat turn; return assistant text and tool calls."""
    response = session.post(chat_url, json=payload, timeout=120, stream=True)
    if response.status_code != 200:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(f'Ollama chat failed ({response.status_code}): {detail}')

    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for raw in response.iter_lines():
        if not raw:
            continue
        try:
            native = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(native, dict):
            continue
        msg = native.get('message') if isinstance(native.get('message'), dict) else {}
        piece = msg.get('content')
        if piece:
            content_parts.append(str(piece))
        if msg.get('tool_calls'):
            tool_calls = _normalize_tool_calls(msg.get('tool_calls'))
        if native.get('done') and msg.get('tool_calls'):
            tool_calls = _normalize_tool_calls(msg.get('tool_calls'))
    return ''.join(content_parts), tool_calls


def _build_native_payload(
    model_name: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any],
    *,
    allow_write: bool,
) -> dict[str, Any]:
    native: dict[str, Any] = {
        'model': model_name,
        'messages': normalize_messages_for_ollama(messages),
        'stream': True,
        'tools': get_tool_definitions(include_write=allow_write),
        'options': options,
    }
    apply_copilot_native_defaults(native, {'tools': native['tools']})
    return native


def stream_ask_agent(
    *,
    session: requests.Session,
    chat_url: str,
    model_name: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any],
    allow_write: bool = False,
) -> Iterator[str]:
    """Yield NDJSON event lines for the Ask? agent UI."""
    working_messages = list(messages)

    try:
        for _ in range(_max_iterations()):
            payload = _build_native_payload(
                model_name,
                working_messages,
                options,
                allow_write=allow_write,
            )
            content, tool_calls = _stream_chat_turn(session, chat_url, payload)

            if content:
                yield json.dumps({'type': 'content', 'text': content}, ensure_ascii=False) + '\n'

            if not tool_calls:
                yield json.dumps({'type': 'done'}, ensure_ascii=False) + '\n'
                return

            assistant_msg: dict[str, Any] = {'role': 'assistant', 'content': content or ''}
            assistant_msg['tool_calls'] = [
                {
                    'id': tc['id'],
                    'type': 'function',
                    'function': {
                        'name': tc['function']['name'],
                        'arguments': json.dumps(tc['function']['arguments'], ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ]
            working_messages.append(assistant_msg)

            for tc in tool_calls:
                fn = tc['function']
                name = fn['name']
                args = fn['arguments']
                call_id = tc['id']
                yield json.dumps(
                    {'type': 'tool_call', 'name': name, 'arguments': args},
                    ensure_ascii=False,
                ) + '\n'
                result = execute_tool(name, args, allow_write=allow_write)
                yield json.dumps(
                    {'type': 'tool_result', 'name': name, 'content': result},
                    ensure_ascii=False,
                ) + '\n'
                working_messages.append({
                    'role': 'tool',
                    'tool_call_id': call_id,
                    'content': result,
                })

        yield json.dumps(
            {'type': 'error', 'message': 'Agent stopped: maximum tool iterations reached'},
            ensure_ascii=False,
        ) + '\n'
    except requests.exceptions.Timeout:
        yield json.dumps({'type': 'error', 'message': 'Request timed out'}, ensure_ascii=False) + '\n'
    except requests.exceptions.ConnectionError:
        yield json.dumps(
            {'type': 'error', 'message': 'Cannot connect to Ollama'},
            ensure_ascii=False,
        ) + '\n'
    except RuntimeError as err:
        yield json.dumps({'type': 'error', 'message': str(err)}, ensure_ascii=False) + '\n'
