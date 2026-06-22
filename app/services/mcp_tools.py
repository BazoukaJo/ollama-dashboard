"""Shared MCP tool registry for dashboard agent mode and IDE MCP server."""
from __future__ import annotations

import json
import os
from typing import Any, Callable

from flask import current_app, has_app_context

from app.services.warm_start import post_warm_start
from app.services.web_tools import (
    fetch_url,
    web_search,
)
from app.services.web_tools import (
    mcp_allow_web as _web_tools_allow_web,
)

ToolHandler = Callable[..., Any]

_WRITE_TOOLS = frozenset({'start_model', 'stop_model'})
_WEB_TOOLS = frozenset({'fetch_url', 'web_search'})


def mcp_allow_write() -> bool:
    return os.getenv('MCP_ALLOW_WRITE', 'false').strip().lower() in ('1', 'true', 'yes', 'on')


def mcp_allow_web() -> bool:
    return _web_tools_allow_web()


def _svc():
    if has_app_context():
        return current_app.config['OLLAMA_SERVICE']
    raise RuntimeError('MCP tools require Flask application context')


def _ollama_generate_url(suffix: str = 'generate') -> str:
    svc = _svc()
    host, port = svc.get_ollama_host_port()
    return f'http://{host}:{port}/api/{suffix}'


def _json_result(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': {
                'type': 'object',
                'properties': properties,
                'required': required or [],
            },
        },
    }


def _handle_list_available_models(_arguments: dict[str, Any]) -> Any:
    models = _svc().get_available_models(force_refresh=False)
    slim = []
    for model in models or []:
        if not isinstance(model, dict):
            continue
        slim.append({
            'name': model.get('name'),
            'size': model.get('size'),
            'has_vision': model.get('has_vision'),
            'has_tools': model.get('has_tools'),
            'has_reasoning': model.get('has_reasoning'),
            'has_moe': model.get('has_moe'),
        })
    return {'models': slim, 'count': len(slim)}


def _handle_list_running_models(_arguments: dict[str, Any]) -> Any:
    models = _svc().get_running_models(force_refresh=True)
    slim = []
    for model in models or []:
        if not isinstance(model, dict):
            continue
        slim.append({
            'name': model.get('name'),
            'size': model.get('size'),
            'expires_at': model.get('expires_at'),
            'has_vision': model.get('has_vision'),
            'has_tools': model.get('has_tools'),
            'has_reasoning': model.get('has_reasoning'),
            'has_moe': model.get('has_moe'),
        })
    return {'models': slim, 'count': len(slim)}


def _handle_get_model_info(arguments: dict[str, Any]) -> Any:
    model_name = str(arguments.get('model_name') or arguments.get('model') or '').strip()
    if not model_name:
        return {'error': 'model_name is required'}
    info = _svc().get_model_info_cached(model_name)
    if not info:
        return {'error': f"Model '{model_name}' not found"}
    return info


def _handle_get_system_stats(_arguments: dict[str, Any]) -> Any:
    return _svc().get_system_stats()


def _handle_get_proxy_status(_arguments: dict[str, Any]) -> Any:
    from app.services.copilot_analytics import client_proxy_status

    data_dir = current_app.config.get('DATA_DIR') or 'data'
    svc = _svc()
    host, port = svc.get_ollama_host_port()
    ollama_base = f'http://{host}:{port}'
    return client_proxy_status(data_dir, ollama_base_url=ollama_base)


def _handle_fetch_url(arguments: dict[str, Any]) -> Any:
    return fetch_url(arguments)


def _handle_web_search(arguments: dict[str, Any]) -> Any:
    return web_search(arguments)


def _handle_start_model(arguments: dict[str, Any]) -> Any:
    model_name = str(arguments.get('model_name') or arguments.get('model') or '').strip()
    if not model_name:
        return {'success': False, 'error': 'model_name is required'}
    if not mcp_allow_write():
        return {'success': False, 'error': 'Write tools disabled (set MCP_ALLOW_WRITE=true)'}
    svc = _svc()
    if not svc.get_service_status():
        return {'success': False, 'error': 'Ollama service is not running'}
    running = svc.get_running_models(force_refresh=True)
    if any(m.get('name') == model_name for m in running):
        return {'success': True, 'message': f'Model {model_name} is already running'}
    response = post_warm_start(svc, _ollama_generate_url(), model_name, timeout=120)
    if response.status_code == 200:
        svc.clear_cache('running_models')
        return {'success': True, 'message': f'Model {model_name} started'}
    if has_app_context():
        current_app.logger.warning(
            'MCP warm start failed for %s: HTTP %s',
            model_name,
            response.status_code,
        )
    return {'success': False, 'error': 'Failed to start model. Check server logs for details.'}


def _handle_stop_model(arguments: dict[str, Any]) -> Any:
    model_name = str(arguments.get('model_name') or arguments.get('model') or '').strip()
    if not model_name:
        return {'success': False, 'error': 'model_name is required'}
    if not mcp_allow_write():
        return {'success': False, 'error': 'Write tools disabled (set MCP_ALLOW_WRITE=true)'}
    svc = _svc()
    if not svc.get_service_status():
        return {'success': False, 'error': 'Ollama service is not running'}
    running = svc.get_running_models(force_refresh=True)
    if not any(m.get('name') == model_name for m in running):
        return {'success': False, 'error': f'Model {model_name} is not currently running'}
    response = svc._session.post(
        _ollama_generate_url(),
        json={'model': model_name, 'prompt': '', 'stream': False, 'keep_alive': 0},
        timeout=30,
    )
    if response.status_code == 200:
        svc.clear_cache('running_models')
        return {'success': True, 'message': f'Model {model_name} stopped'}
    try:
        detail = response.json()
    except ValueError:
        detail = response.text
    return {'success': False, 'error': detail}


_TOOL_SPECS: list[dict[str, Any]] = [
    {
        'name': 'list_available_models',
        'description': 'List installed Ollama models with capability flags.',
        'write': False,
        'schema': _tool('list_available_models', 'List installed Ollama models with capability flags.', {}),
        'handler': _handle_list_available_models,
    },
    {
        'name': 'list_running_models',
        'description': 'List models currently loaded in Ollama memory.',
        'write': False,
        'schema': _tool('list_running_models', 'List models currently loaded in Ollama memory.', {}),
        'handler': _handle_list_running_models,
    },
    {
        'name': 'get_model_info',
        'description': 'Get metadata and capabilities for one model by name.',
        'write': False,
        'schema': _tool(
            'get_model_info',
            'Get metadata and capabilities for one model by name.',
            {'model_name': {'type': 'string', 'description': 'Ollama model tag, e.g. llama3.2:3b'}},
            ['model_name'],
        ),
        'handler': _handle_get_model_info,
    },
    {
        'name': 'get_system_stats',
        'description': 'Return CPU, RAM, and GPU/VRAM usage snapshot for this machine.',
        'write': False,
        'schema': _tool(
            'get_system_stats',
            'Return CPU, RAM, and GPU/VRAM usage snapshot for this machine.',
            {},
        ),
        'handler': _handle_get_system_stats,
    },
    {
        'name': 'get_proxy_status',
        'description': 'Summarize external IDE proxy activity (VS Code, Cursor, Continue).',
        'write': False,
        'schema': _tool(
            'get_proxy_status',
            'Summarize external IDE proxy activity (VS Code, Cursor, Continue).',
            {},
        ),
        'handler': _handle_get_proxy_status,
    },
    {
        'name': 'fetch_url',
        'description': 'Fetch a public web page and return readable text (requires MCP_ALLOW_WEB=true).',
        'write': False,
        'web': True,
        'schema': _tool(
            'fetch_url',
            'Fetch a public HTTP(S) page and return extracted text content.',
            {'url': {'type': 'string', 'description': 'Public http(s) URL to fetch'}},
            ['url'],
        ),
        'handler': _handle_fetch_url,
    },
    {
        'name': 'web_search',
        'description': 'Search the public web and return result titles and URLs (requires MCP_ALLOW_WEB=true).',
        'write': False,
        'web': True,
        'schema': _tool(
            'web_search',
            'Search the public web via DuckDuckGo and return titles and URLs.',
            {
                'query': {'type': 'string', 'description': 'Search query'},
                'max_results': {
                    'type': 'integer',
                    'description': 'Maximum number of results (default 5)',
                },
            },
            ['query'],
        ),
        'handler': _handle_web_search,
    },
    {
        'name': 'start_model',
        'description': 'Load a model into Ollama memory (requires MCP_ALLOW_WRITE=true).',
        'write': True,
        'schema': _tool(
            'start_model',
            'Load a model into Ollama memory.',
            {'model_name': {'type': 'string', 'description': 'Ollama model tag to load'}},
            ['model_name'],
        ),
        'handler': _handle_start_model,
    },
    {
        'name': 'stop_model',
        'description': 'Unload a model from Ollama memory (requires MCP_ALLOW_WRITE=true).',
        'write': True,
        'schema': _tool(
            'stop_model',
            'Unload a model from Ollama memory.',
            {'model_name': {'type': 'string', 'description': 'Ollama model tag to unload'}},
            ['model_name'],
        ),
        'handler': _handle_stop_model,
    },
]

_HANDLERS: dict[str, ToolHandler] = {spec['name']: spec['handler'] for spec in _TOOL_SPECS}


def list_tools_metadata(
    *,
    include_write: bool | None = None,
    include_web: bool | None = None,
) -> list[dict[str, Any]]:
    """Return tool catalog for Connect panel and status API."""
    allow_write = mcp_allow_write() if include_write is None else include_write
    allow_web = mcp_allow_web() if include_web is None else include_web
    out: list[dict[str, Any]] = []
    for spec in _TOOL_SPECS:
        if spec['write'] and not allow_write:
            continue
        if spec.get('web') and not allow_web:
            continue
        out.append({
            'name': spec['name'],
            'description': spec['description'],
            'write': bool(spec['write']),
            'web': bool(spec.get('web')),
        })
    return out


def get_tool_definitions(
    *,
    include_write: bool | None = None,
    include_web: bool | None = None,
) -> list[dict[str, Any]]:
    """Ollama-native tool definitions for /api/chat."""
    allow_write = mcp_allow_write() if include_write is None else include_write
    allow_web = mcp_allow_web() if include_web is None else include_web
    tools: list[dict[str, Any]] = []
    for spec in _TOOL_SPECS:
        if spec['write'] and not allow_write:
            continue
        if spec.get('web') and not allow_web:
            continue
        tools.append(spec['schema'])
    return tools


def execute_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    allow_write: bool | None = None,
    allow_web: bool | None = None,
) -> str:
    """Dispatch a tool call and return JSON string for role=tool messages."""
    tool_name = str(name or '').strip()
    handler = _HANDLERS.get(tool_name)
    if not handler:
        return _json_result({'error': f'Unknown tool: {tool_name}'})
    if tool_name in _WRITE_TOOLS:
        write_ok = mcp_allow_write() if allow_write is None else allow_write
        if not write_ok:
            return _json_result({'error': 'Write tools disabled (set MCP_ALLOW_WRITE=true)'})
    if tool_name in _WEB_TOOLS:
        web_ok = mcp_allow_web() if allow_web is None else allow_web
        if not web_ok:
            return _json_result({'error': 'Web tools disabled (set MCP_ALLOW_WEB=true)'})
    args = arguments if isinstance(arguments, dict) else {}
    try:
        result = handler(args)
        return _json_result(result)
    except Exception as err:  # pylint: disable=broad-except
        if has_app_context():
            current_app.logger.warning('MCP tool %s failed: %s', tool_name, err)
        return _json_result({'error': 'Tool execution failed. Check server logs for details.'})
