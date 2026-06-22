"""Ask? agent mode — server-side Ollama /api/chat tool loop using MCP tool registry."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Iterator

import requests

from app.services.client_payload_compat import normalize_messages_for_ollama
from app.services.error_messages import log_upstream_error
from app.services.mcp_tools import execute_tool, get_tool_definitions, mcp_allow_web
from app.services.v1_native_bridge import _assistant_reasoning_piece, apply_copilot_native_defaults

logger = logging.getLogger(__name__)


def _model_supports_tools(model_info: dict[str, Any]) -> bool:
    if not isinstance(model_info, dict):
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


def _ensure_agent_system_message(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(str(m.get('role') or '').lower() == 'system' for m in messages):
        return messages
    lines = [
        'You are a helpful assistant with access to dashboard tools.',
        'When the user asks about current events, live data, prices, weather, or anything that '
        'requires up-to-date information, use web_search first, then fetch_url on the best result.',
    ]
    if mcp_allow_web():
        lines.append(
            'Web tools: web_search (search the public web) and fetch_url (read a public page). '
            'Prefer these over guessing when freshness matters.'
        )
    lines.append(
        'Other tools: list_available_models, list_running_models, get_model_info, '
        'get_system_stats, get_proxy_status.'
    )
    return [{'role': 'system', 'content': ' '.join(lines)}] + list(messages)


def _max_iterations() -> int:
    try:
        return max(1, min(int(os.getenv('ASK_AGENT_MAX_ITERATIONS', '8')), 20))
    except (TypeError, ValueError):
        return 8


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(os.getenv(name, str(default))), maximum))
    except (TypeError, ValueError):
        return default


def _max_consecutive_tool_errors() -> int:
    """Stop the agent after this many turns where every tool call returned an error."""
    return _env_int('ASK_AGENT_MAX_TOOL_ERRORS', 3, minimum=1, maximum=10)


def _max_tool_call_repeats() -> int:
    """Stop the agent after the model repeats the exact same tool call(s) this many times."""
    return _env_int('ASK_AGENT_MAX_TOOL_REPEATS', 3, minimum=2, maximum=10)


def _tool_calls_signature(tool_calls: list[dict[str, Any]]) -> str | None:
    """Stable signature of a turn's tool calls so we can detect a no-progress loop."""
    try:
        parts = sorted(
            (
                str(tc['function']['name']),
                json.dumps(tc['function']['arguments'], sort_keys=True, ensure_ascii=False),
            )
            for tc in tool_calls
        )
        return json.dumps(parts, ensure_ascii=False)
    except (KeyError, TypeError, ValueError):
        return None


def _tool_result_is_error(result: str) -> bool:
    """True when a tool result JSON signals failure (``error`` key or ``success: false``)."""
    try:
        obj = json.loads(result)
    except (TypeError, ValueError):
        return False
    if isinstance(obj, dict):
        return bool(obj.get('error')) or obj.get('success') is False
    return False


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


def _agent_turn_timeout() -> int:
    return _env_int('ASK_AGENT_TURN_TIMEOUT', 180, minimum=30, maximum=900)


def _iter_chat_turn_events(
    session,
    chat_url: str,
    payload: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Stream one /api/chat turn; yield content/thinking chunks then a turn_end summary."""
    response = session.post(
        chat_url, json=payload, timeout=_agent_turn_timeout(), stream=True,
    )
    if response.status_code != 200:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        log_upstream_error(
            logger,
            status_code=response.status_code,
            detail=detail,
            context='ask agent chat turn',
        )
        raise RuntimeError(
            f'Ollama chat failed ({response.status_code}). Check server logs for details.'
        )

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
            text = str(piece)
            content_parts.append(text)
            yield {'type': 'content', 'text': text}
        reasoning = _assistant_reasoning_piece(msg)
        if reasoning:
            yield {'type': 'thinking', 'text': reasoning}
        if msg.get('tool_calls'):
            tool_calls = _normalize_tool_calls(msg.get('tool_calls'))
        if native.get('done') and msg.get('tool_calls'):
            tool_calls = _normalize_tool_calls(msg.get('tool_calls'))
    yield {
        'type': 'turn_end',
        'content': ''.join(content_parts),
        'tool_calls': tool_calls,
    }


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
    working_messages = _ensure_agent_system_message(list(messages))
    max_tool_errors = _max_consecutive_tool_errors()
    max_repeats = _max_tool_call_repeats()
    consecutive_error_turns = 0
    last_signature: str | None = None
    repeat_count = 0

    try:
        for iteration in range(1, _max_iterations() + 1):
            yield json.dumps(
                {
                    'type': 'status',
                    'phase': 'model_turn',
                    'iteration': iteration,
                    'max_iterations': _max_iterations(),
                    'message': f'Agent turn {iteration}/{_max_iterations()}…',
                },
                ensure_ascii=False,
            ) + '\n'
            payload = _build_native_payload(
                model_name,
                working_messages,
                options,
                allow_write=allow_write,
            )
            content = ''
            tool_calls: list[dict[str, Any]] = []
            for event in _iter_chat_turn_events(session, chat_url, payload):
                if event['type'] in ('content', 'thinking'):
                    yield json.dumps(event, ensure_ascii=False) + '\n'
                elif event['type'] == 'turn_end':
                    content = str(event.get('content') or '')
                    tool_calls = event.get('tool_calls') or []

            if not tool_calls:
                yield json.dumps({'type': 'done'}, ensure_ascii=False) + '\n'
                return

            # Loop breaker: the model asking for the exact same tool call(s) over and over makes
            # no progress and would otherwise burn every iteration — stop early with a clear note.
            signature = _tool_calls_signature(tool_calls)
            if signature is not None and signature == last_signature:
                repeat_count += 1
            else:
                repeat_count = 1
                last_signature = signature
            if repeat_count >= max_repeats:
                yield json.dumps(
                    {
                        'type': 'error',
                        'message': (
                            'Agent stopped: the model repeated the same tool call '
                            f'{repeat_count} times without making progress.'
                        ),
                    },
                    ensure_ascii=False,
                ) + '\n'
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

            turn_error_count = 0
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
                if _tool_result_is_error(result):
                    turn_error_count += 1
                yield json.dumps(
                    {'type': 'tool_result', 'name': name, 'content': result},
                    ensure_ascii=False,
                ) + '\n'
                working_messages.append({
                    'role': 'tool',
                    'tool_call_id': call_id,
                    'content': result,
                })

            # Error breaker: if every tool in a turn failed, several turns running, the model is
            # unlikely to recover on its own — stop instead of looping to the iteration cap.
            if tool_calls and turn_error_count == len(tool_calls):
                consecutive_error_turns += 1
            else:
                consecutive_error_turns = 0
            if consecutive_error_turns >= max_tool_errors:
                yield json.dumps(
                    {
                        'type': 'error',
                        'message': (
                            'Agent stopped: tool calls failed '
                            f'{consecutive_error_turns} turns in a row.'
                        ),
                    },
                    ensure_ascii=False,
                ) + '\n'
                return

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
