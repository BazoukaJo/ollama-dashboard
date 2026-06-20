"""Embedded MCP Streamable HTTP server mounted at /mcp on the dashboard port."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Module-private MCP singletons (lazy init — not UPPER_CASE constants).
_mcp_instance = None  # pylint: disable=invalid-name
_mcp_asgi_app = None  # pylint: disable=invalid-name


def _build_mcp():
    from mcp.server.fastmcp import FastMCP

    from app.services import mcp_tools

    mcp = FastMCP(
        'ollama-dashboard',
        stateless_http=True,
        streamable_http_path='/',
    )

    @mcp.tool()
    def list_available_models() -> str:
        """List installed Ollama models with capability flags."""
        return mcp_tools.execute_tool('list_available_models', {})

    @mcp.tool()
    def list_running_models() -> str:
        """List models currently loaded in Ollama memory."""
        return mcp_tools.execute_tool('list_running_models', {})

    @mcp.tool()
    def get_model_info(model_name: str) -> str:
        """Get metadata and capabilities for one model by name."""
        return mcp_tools.execute_tool('get_model_info', {'model_name': model_name})

    @mcp.tool()
    def get_system_stats() -> str:
        """Return CPU, RAM, and GPU/VRAM usage snapshot for this machine."""
        return mcp_tools.execute_tool('get_system_stats', {})

    @mcp.tool()
    def get_proxy_status() -> str:
        """Summarize external IDE proxy activity (VS Code, Cursor, Continue)."""
        return mcp_tools.execute_tool('get_proxy_status', {})

    if mcp_tools.mcp_allow_write():

        @mcp.tool()
        def start_model(model_name: str) -> str:
            """Load a model into Ollama memory."""
            return mcp_tools.execute_tool('start_model', {'model_name': model_name})

        @mcp.tool()
        def stop_model(model_name: str) -> str:
            """Unload a model from Ollama memory."""
            return mcp_tools.execute_tool('stop_model', {'model_name': model_name})

    return mcp


def get_mcp_asgi_app():
    """Lazy-build the Streamable HTTP ASGI sub-application."""
    global _mcp_instance, _mcp_asgi_app
    if _mcp_asgi_app is None:
        _mcp_instance = _build_mcp()
        _mcp_asgi_app = _mcp_instance.streamable_http_app()
    return _mcp_asgi_app


def mount_mcp_on_flask_app(flask_app) -> None:
    """Mount MCP at /mcp via WSGI dispatcher (same port as dashboard)."""
    try:
        from typing import cast

        from a2wsgi import ASGIMiddleware
        from a2wsgi.asgi_typing import ASGIApp
        from werkzeug.middleware.dispatcher import DispatcherMiddleware
    except ImportError as err:
        logger.warning('MCP mount skipped (missing dependency): %s', err)
        return

    mcp_wsgi = ASGIMiddleware(cast(ASGIApp, get_mcp_asgi_app()))
    flask_app.wsgi_app = DispatcherMiddleware(
        flask_app.wsgi_app,
        {'/mcp': cast(Any, mcp_wsgi)},
    )
    logger.info('MCP Streamable HTTP mounted at /mcp')


def mcp_health_check(flask_app) -> dict[str, Any]:
    """Lightweight probe used by Connect wizard (no full MCP handshake)."""
    try:
        get_mcp_asgi_app()
        with flask_app.app_context():
            tools = __import__('app.services.mcp_tools', fromlist=['list_tools_metadata']).list_tools_metadata()
        return {
            'ok': True,
            'tool_count': len(tools),
            'write_tools_enabled': __import__(
                'app.services.mcp_tools', fromlist=['mcp_allow_write']
            ).mcp_allow_write(),
        }
    except Exception as err:  # pylint: disable=broad-except
        return {'ok': False, 'error': str(err)}
