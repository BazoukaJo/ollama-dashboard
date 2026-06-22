"""Shared helpers and globals for main blueprint routes."""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from flask import Response, current_app, jsonify, request

from app.services.error_messages import log_upstream_error
from app.services.ollama_core import OllamaServiceCore
from app.services.ollama_models import OllamaConnectionError
from app.services.service_errors import HTTP_SERVICE_ERRORS
from app.services.validators import InputValidator

# Set by init_app from app.config['OLLAMA_SERVICE']; tests patch app.routes.main.ollama_service
ollama_service = None
_ROUTE_ERRORS = HTTP_SERVICE_ERRORS + (OllamaConnectionError,)


def _get_ollama_service():
    """Get OllamaService from app context (injected by create_app)."""
    try:
        from app.routes import main as main_routes  # pylint: disable=import-outside-toplevel

        if main_routes.ollama_service is not None:
            return main_routes.ollama_service
    except (ImportError, AttributeError):
        pass
    if ollama_service is not None:
        return ollama_service
    return current_app.config['OLLAMA_SERVICE']

def _models_force_refresh() -> bool:
    """True when client asks for a fresh Ollama catalog read (?refresh=1)."""
    q = request.args.get('refresh', '').strip().lower()
    return q in ('1', 'true', 'yes')


def _get_timezone_name():
    """Get the local timezone name in a reliable way."""
    try:
        return datetime.now().astimezone().tzname()
    except (OSError, ValueError, AttributeError, IndexError, TypeError):
        try:
            # Fallback to time module
            return time.tzname[0] if time.tzname and len(time.tzname) > 0 else 'UTC'
        except (AttributeError, IndexError, TypeError):
            # Last resort
            return 'UTC'


def _normalize_ollama_host_port_for_display(raw_host, raw_port):
    """If OLLAMA_HOST is host:port, use that port once (avoid 127.0.0.1:11434:11434 in UI)."""
    host = OllamaServiceCore._clean_ollama_host_string(str(raw_host or 'localhost'))
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = 11434
    if isinstance(host, str) and host.count(':') == 1:
        host_part, _, port_part = host.partition(':')
        if host_part and port_part and str(port_part).strip().isdigit():
            try:
                port = int(port_part)
                host = host_part
            except (ValueError, TypeError):
                pass
    return host, port


def _format_ollama_host_port_label(host, port):
    """Host:port label for UI (brackets IPv6 literals)."""
    host = OllamaServiceCore._clean_ollama_host_string(str(host or 'localhost'))
    port = int(port)
    if ':' in host and not host.startswith('['):
        host = f'[{host}]'
    return f'{host}:{port}'


def _format_ollama_api_base(host, port):
    """Full Ollama backend URL shown in the dashboard header."""
    return f'http://{_format_ollama_host_port_label(host, port)}'.rstrip('/')


def _format_proxy_endpoint_label(url: str) -> str:
    """Proxy endpoint for header display (scheme omitted, like host:port/path)."""
    return re.sub(r'^https?://', '', (url or '').strip(), count=1, flags=re.IGNORECASE)


def _proxy_ui_template_vars():
    base = request.host_url.rstrip('/') + '/ollama'
    return {
        'proxy_endpoint': base,
        'proxy_endpoint_label': _format_proxy_endpoint_label(base),
    }


def _ollama_ui_template_vars():
    """Expose Ollama host/port to the UI (matches service outbound host/port)."""
    try:
        host, port = _get_ollama_service()._get_ollama_host_port()
    except _ROUTE_ERRORS:
        host, port = _normalize_ollama_host_port_for_display(
            current_app.config.get('OLLAMA_HOST', 'localhost'),
            current_app.config.get('OLLAMA_PORT', 11434),
        )
    port = int(port)
    return {
        'ollama_public_host': host,
        'ollama_public_port': port,
        'ollama_host_port_label': _format_ollama_host_port_label(host, port),
        'ollama_api_base': _format_ollama_api_base(host, port),
    }


def _ollama_installed_for_dashboard(svc, update_result):
    """Whether to hide the Install button: binary on disk or API reported a real version.

    After updates, PATH seen by the dashboard process may not include ``ollama`` while
    ``/api/version`` still works — without this, users see both a version badge and Install.
    """
    if svc is not None:
        try:
            if svc.is_ollama_installed():
                return True
        except _ROUTE_ERRORS:
            pass
    ver = (update_result or {}).get('current_version') or ''
    v = (ver or '').strip()
    return bool(v and v.lower() != 'unknown')

def _get_ollama_url(endpoint=""):
    """Generate Ollama API URL (host may not include :port; see _normalize_ollama_host_port_for_display)."""
    try:
        host, port = _get_ollama_service()._get_ollama_host_port()
    except _ROUTE_ERRORS:
        host, port = _normalize_ollama_host_port_for_display(
            current_app.config.get('OLLAMA_HOST', 'localhost'),
            current_app.config.get('OLLAMA_PORT', 11434),
        )
    return f"http://{host}:{int(port)}/api/{endpoint}"


def _merge_model_chat_options(model_name: str) -> dict[str, Any]:
    options = _get_ollama_service().get_default_settings()
    try:
        model_settings_entry = _get_ollama_service().get_model_settings_with_fallback(model_name)
        if model_settings_entry and isinstance(model_settings_entry.get('settings'), dict):
            for k, v in model_settings_entry['settings'].items():
                options[k] = v
    except _ROUTE_ERRORS as e:
        current_app.logger.error("Failed to merge per-model settings for %s: %s", model_name, e)
    return options


def _rate_limit_response(limiter_key: str) -> tuple[dict[str, Any], int] | None:
    """Return a 429 JSON body when the rate limiter rejects the request."""
    ok, msg = _get_ollama_service().consume_rate_limit(limiter_key)
    if ok:
        return None
    body = {'success': False, 'message': msg, 'error': msg}
    return body, 429

def _validate_model_name(model_name: str) -> tuple[dict[str, Any] | None, int | None]:
    """Validate model name format. Returns (None, None) if valid, or (error_dict, status_code) if invalid."""
    is_valid, msg = InputValidator.validate_model_name(model_name)
    if not is_valid:
        return {"success": False, "error": msg, "message": msg}, 400
    return None, None


def _resolve_main_patch(export_name: str, wrapper, impl):
    """Use app.routes.main export when tests patch it; otherwise run impl."""
    try:
        from app.routes import main as main_mod  # pylint: disable=import-outside-toplevel

        fn = getattr(main_mod, export_name)
        if fn is not wrapper:
            return fn
    except (ImportError, AttributeError):
        pass
    return impl


def _verify_model_unloaded_impl(model_name, max_attempts=5, delay_seconds=1):
    """Poll /api/ps to confirm model is no longer loaded. Returns True when verified gone."""
    for _ in range(max_attempts):
        try:
            # Use the shared session from the service to honour connection pooling
            resp = _get_ollama_service()._session.get(_get_ollama_url("ps"), timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                if not any(m.get("name") == model_name for m in models):
                    return True
        except _ROUTE_ERRORS:
            pass
        time.sleep(delay_seconds)
    return False


def _verify_model_unloaded(model_name, max_attempts=5, delay_seconds=1):
    fn = _resolve_main_patch('_verify_model_unloaded', _verify_model_unloaded, _verify_model_unloaded_impl)
    return fn(model_name, max_attempts=max_attempts, delay_seconds=delay_seconds)


def _handle_model_error(response, model_name, operation="operation") -> tuple[dict[str, Any], int]:
    """Handle common model operation errors."""
    error_text = response.text.lower()

    if "exit status 2" in error_text or "llama runner process has terminated" in error_text:
        return {
            "success": False,
            "message": f"Model '{model_name}' is incompatible with your system. Try 'llama2:latest' or 'deepseek-r1:8b'."
        }, 400

    if "not found" in error_text:
        return {
            "success": False,
            "message": f"Model '{model_name}' not found. Please ensure it's installed."
        }, 404

    if "memory" in error_text.lower() or "ram" in error_text.lower():
        return {
            "success": False,
            "message": f"Model '{model_name}' is too large for available memory. Try a smaller model."
        }, 400

    status_code = getattr(response, "status_code", None)
    log_upstream_error(
        current_app.logger,
        status_code=status_code,
        detail=(response.text or '')[:500],
        context=f"model {model_name} {operation}",
    )
    return {
        "success": False,
        "message": f"Failed to {operation} model '{model_name}'. Check server logs for details.",
    }, int(status_code) if status_code else 500
def _force_unload_via_ollama_restart(model_name):
    """Force-kill and restart Ollama to unload all models (escape hatch for stuck loads)."""
    svc = _get_ollama_service()
    restart_result = svc.restart_service()
    memory_cleared = bool(restart_result.get('memory_cleared')) or not svc.get_service_status()

    def _refresh_running_cache():
        svc.clear_cache('running_models')
        try:
            svc.get_running_models(force_refresh=True)
        except _ROUTE_ERRORS:
            pass

    if restart_result.get('success'):
        _refresh_running_cache()
        return {
            "success": True,
            "message": (
                f"Model {model_name} force-unloaded — Ollama was restarted and all models were cleared from memory."
            ),
        }, 200

    if memory_cleared:
        _refresh_running_cache()
        retry = svc.start_service()
        if retry.get('success'):
            try:
                svc.get_running_models(force_refresh=True)
            except _ROUTE_ERRORS:
                pass
            return {
                "success": True,
                "message": (
                    f"Model {model_name} force-unloaded — Ollama was restarted and all models were cleared from memory."
                ),
            }, 200
        return {
            "success": True,
            "memory_cleared": True,
            "restart_required": True,
            "message": (
                f"Model {model_name} was cleared from memory (Ollama stopped). "
                f"Automatic restart failed: {restart_result.get('message', 'unknown error')}. "
                "Use Start Service in the dashboard to bring Ollama back."
            ),
        }, 200

    return {
        "success": False,
        "message": (
            f"Could not force-unload {model_name}: "
            f"{restart_result.get('message', 'Ollama restart failed')}"
        ),
    }, 500
def _resolve_model_name(model_name: str | None = None) -> tuple[str | None, tuple[dict[str, Any], int] | None]:
    """Get model name from path param or ?model= query param."""
    name = model_name or request.args.get('model') or request.args.get('name')
    if not name:
        return None, ({"success": False, "error": "Missing model name"}, 400)
    err, status = _validate_model_name(name)
    if err is not None:
        return None, (err, status or 400)
    return name, None


def _verify_model_deleted_impl(model_name, max_attempts=5, delay_seconds=1):
    """Poll /api/tags to confirm model is no longer in the list. Returns True when verified gone."""
    for _ in range(max_attempts):
        try:
            available = _get_ollama_service().get_available_models(force_refresh=True)
            names = [m.get("name") for m in available if m.get("name")]
            if not any(n == model_name or n.startswith(model_name + ":") for n in names):
                return True
        except _ROUTE_ERRORS:
            pass
        time.sleep(delay_seconds)
    return False


def _verify_model_deleted(model_name, max_attempts=5, delay_seconds=1):
    fn = _resolve_main_patch('_verify_model_deleted', _verify_model_deleted, _verify_model_deleted_impl)
    return fn(model_name, max_attempts=max_attempts, delay_seconds=delay_seconds)


def _json_success(message: str, extra: dict[str, Any] | None = None, status: int = 200) -> tuple[Response, int]:
    payload = {"success": True, "message": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status

def _json_error(message: str, status: int = 500) -> tuple[Response, int]:
    """Return a standardized JSON error response."""
    return jsonify({"success": False, "error": message, "message": message}), status
