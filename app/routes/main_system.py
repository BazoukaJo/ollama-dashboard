"""System and service control API routes for the main blueprint."""
from __future__ import annotations

import app.routes.main as main_routes
from app.routes import bp
from app.routes.main import (
    _ROUTE_ERRORS,
)


@bp.route('/api/system/stats')
def get_system_stats():
    """Get current system statistics."""
    try:
        stats = main_routes._get_ollama_service().get_system_stats()
        return stats if stats else ({"error": "System monitoring not available"}, 503)
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500

@bp.route('/api/version')
def get_ollama_version():
    """Get Ollama version."""
    try:
        version = main_routes._get_ollama_service().get_ollama_version()
        return {"version": version}
    except _ROUTE_ERRORS as e:
        return {"error": str(e), "version": "Unknown"}, 500

@bp.route('/api/system/stats/history')
def get_system_stats_history():
    """Get historical system statistics."""
    try:
        history = main_routes._get_ollama_service().get_system_stats_history()
        return {"history": history}
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/service/status')
def get_service_status():
    """Get Ollama service status."""
    try:
        status = main_routes._get_ollama_service().get_service_status() or False
        return {"status": "running" if status else "stopped", "running": status}
    except _ROUTE_ERRORS as e:
        return {"error": str(e), "status": "unknown", "running": False}, 500

@bp.route('/api/health')
def api_health():
    """Component health: background thread, cache ages, failure counters."""
    try:
        return main_routes._get_ollama_service().get_component_health()
    except _ROUTE_ERRORS as e:
        return {"error": str(e)}, 500


@bp.route('/api/service/start', methods=['POST'])
def start_service():
    """Start the Ollama service."""
    try:
        result = main_routes._get_ollama_service().start_service() or {}
        if not result:
            return {"success": False, "message": "Service start returned no result"}, 500
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except _ROUTE_ERRORS as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/service/stop', methods=['POST'])
def stop_service():
    """Stop the Ollama service."""
    try:
        result = main_routes._get_ollama_service().stop_service()
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except _ROUTE_ERRORS as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}, 500


@bp.route('/api/service/restart', methods=['POST'])
def restart_service():
    """Restart the Ollama service."""
    try:
        result = main_routes._get_ollama_service().restart_service()
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except _ROUTE_ERRORS as e:
        return {"success": False, "message": f"Unexpected error restarting service: {str(e)}"}, 500


@bp.route('/api/service/update-ollama', methods=['POST'])
def update_ollama():
    """Stop Ollama, run platform upgrade (winget/brew/install.sh), then start again."""
    try:
        result = main_routes._get_ollama_service().update_ollama()
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except _ROUTE_ERRORS as e:
        return {"success": False, "message": f"Unexpected error updating Ollama: {str(e)}"}, 500


@bp.route('/api/service/install-ollama', methods=['POST'])
def install_ollama():
    """Install Ollama via winget/choco/brew/install.sh when not detected, then start service."""
    try:
        result = main_routes._get_ollama_service().install_ollama()
        return (result, 200) if isinstance(result, dict) and result.get("success") else (result, 500)
    except _ROUTE_ERRORS as e:
        return {"success": False, "message": f"Unexpected error installing Ollama: {str(e)}"}, 500


@bp.route('/api/full/restart', methods=['POST'])
def full_restart():
    """Perform comprehensive application restart (caches + settings + background thread). Does NOT restart Ollama service."""
    try:
        result = main_routes._get_ollama_service().full_restart()
        return (result, 200) if result.get("success") else (result, 500)
    except _ROUTE_ERRORS as e:
        return {"success": False, "message": f"Unexpected error performing full restart: {str(e)}"}, 500

