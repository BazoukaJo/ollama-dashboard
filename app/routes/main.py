"""
Main routes blueprint for Ollama Dashboard.

Route handlers are split across main_pages, main_models, main_chat, and main_system;
shared helpers live in main_common. This module re-exports symbols for test compatibility.
"""
# ruff: noqa: I001 — route submodule imports must follow re-exports (circular-import safe order).
from __future__ import annotations

from app.routes import bp
from app.routes.main_common import (  # noqa: F401 — re-exported for test patching
    _ROUTE_ERRORS,
    _force_unload_via_ollama_restart,
    _format_ollama_api_base,
    _format_ollama_host_port_label,
    _format_proxy_endpoint_label,
    _get_ollama_service,
    _get_ollama_url,
    _get_timezone_name,
    _handle_model_error,
    _json_error,
    _json_success,
    _merge_model_chat_options,
    _models_force_refresh,
    _normalize_ollama_host_port_for_display,
    _ollama_installed_for_dashboard,
    _ollama_ui_template_vars,
    _proxy_ui_template_vars,
    _rate_limit_response,
    _resolve_model_name,
    _validate_model_name,
    _verify_model_deleted,
    _verify_model_unloaded,
    ollama_service,
)
from app.services.ollama_update_check import run_startup_ollama_update_check  # noqa: F401

# Side-effect: register route handlers on bp (must follow re-exports above).
from app.routes import main_chat  # noqa: F401,E402
from app.routes import main_models  # noqa: F401,E402
from app.routes import main_pages  # noqa: F401,E402
from app.routes import main_system  # noqa: F401,E402


def init_app(app):
    """Initialize the blueprint with the app."""
    import app.routes.main_common as main_common  # pylint: disable=import-outside-toplevel

    global ollama_service
    svc = app.config['OLLAMA_SERVICE']
    ollama_service = svc  # For test compatibility (tests patch app.routes.main.ollama_service)
    main_common.ollama_service = svc
    # init_app() is the canonical place to call OllamaService.init_app(); do not duplicate it here.
    # Monitoring endpoints are stored on the blueprint object so they are only registered once
    # even when create_app() is called multiple times (e.g. in tests).
    if not getattr(bp, '_monitoring_registered', False):
        from app.routes.monitoring import create_monitoring_endpoints  # pylint: disable=import-outside-toplevel

        create_monitoring_endpoints(bp, svc)
        bp._monitoring_registered = True  # type: ignore[attr-defined]
    # Template filters (`datetime` and `time_ago`) are registered in app factory via app.__init__.
    # Avoid duplicate registration here to prevent platform-specific filter overrides.
    app.register_blueprint(bp)
    from app.routes.proxy import bp as proxy_bp  # pylint: disable=import-outside-toplevel

    app.register_blueprint(proxy_bp)
    from app.routes.api_proxy import bp as api_proxy_bp  # pylint: disable=import-outside-toplevel

    app.register_blueprint(api_proxy_bp)
