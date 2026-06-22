"""Page and lightweight monitoring routes for the main blueprint."""
from __future__ import annotations

import os
import platform
import signal
import time

import psutil
from flask import jsonify, render_template

import app.routes.main as main_routes
from app import __version__ as DASHBOARD_VERSION
from app.routes import bp
from app.routes.main import (
    _ROUTE_ERRORS,
    _get_timezone_name,
    _ollama_installed_for_dashboard,
    _ollama_ui_template_vars,
    _proxy_ui_template_vars,
)
from app.services.model_helpers import (
    attach_last_token_usage_to_model,
    attach_request_context_to_model,
    normalize_context_display_fields,
)


@bp.route('/')
def index():

    try:
        svc = main_routes._get_ollama_service()
        running_models = svc.get_running_models(force_refresh=False)
        available_models = svc.get_available_models()
        svc.refresh_model_settings_cache_from_disk()
        for _m in running_models or []:
            _m['has_custom_settings'] = svc.has_custom_model_settings(_m.get('name'))
            attach_request_context_to_model(svc, _m)
            attach_last_token_usage_to_model(svc, _m)
            normalize_context_display_fields(_m)
        for _m in available_models or []:
            _m['has_custom_settings'] = svc.has_custom_model_settings(_m.get('name'))
            attach_request_context_to_model(svc, _m)
            attach_last_token_usage_to_model(svc, _m)
            normalize_context_display_fields(_m)
        system_stats = svc.get_system_stats()
        _upd = main_routes.run_startup_ollama_update_check(svc, refresh_installed_version=True)
        version = _upd.get('current_version') or 'Unknown'
        ollama_installed = _ollama_installed_for_dashboard(svc, _upd)
        return render_template(
            'index.html',
            models=running_models,
            available_models=available_models,
            system_stats=system_stats,
            error=None,
            timezone=_get_timezone_name(),
            ollama_version=version,
            ollama_installed=ollama_installed,
            ollama_update_available=bool(_upd.get('update_available')),
            ollama_update_latest_version=_upd.get('latest_version'),
            dashboard_version=DASHBOARD_VERSION,
            timestamp=int(time.time()),
            **_ollama_ui_template_vars(),
            **_proxy_ui_template_vars(),
        )
    except _ROUTE_ERRORS as e:
        empty_stats = {
            'cpu_percent': 0,
            'memory': {'percent': 0, 'total': 0, 'available': 0, 'used': 0},
            'vram': {'percent': 0, 'total': 0, 'used': 0, 'free': 0, 'gpu_3d': 0},
            'disk': {'activity_percent': 0},
        }
        _upd = {'update_available': False, 'latest_version': None}
        try:
            _upd = main_routes.run_startup_ollama_update_check(
                main_routes._get_ollama_service(),
                refresh_installed_version=True,
            )
        except _ROUTE_ERRORS:
            pass
        try:
            svc_err = main_routes._get_ollama_service()
        except _ROUTE_ERRORS:
            svc_err = None
        ollama_installed = _ollama_installed_for_dashboard(svc_err, _upd)
        version_err = _upd.get('current_version') or 'Unknown'
        return render_template(
            'index.html',
            models=[],
            available_models=[],
            system_stats=empty_stats,
            error=str(e),
            timezone=_get_timezone_name(),
            ollama_version=version_err,
            ollama_installed=ollama_installed,
            ollama_update_available=bool(_upd.get('update_available')),
            ollama_update_latest_version=_upd.get('latest_version'),
            dashboard_version=DASHBOARD_VERSION,
            timestamp=int(time.time()),
            **_ollama_ui_template_vars(),
            **_proxy_ui_template_vars(),
        )

@bp.route('/api/test')
def test():
    return {"message": "API is working"}
@bp.route('/api/force_kill', methods=['POST'])
def force_kill_app():
    """Force kill the dashboard app and all its child processes."""
    current_pid = os.getpid()
    parent = psutil.Process(current_pid)
    killed_pids = []
    for child in parent.children(recursive=True):
        try:
            child.kill()
            killed_pids.append(child.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    try:
        parent.kill()
        killed_pids.append(current_pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        try:
            if platform.system() != "Windows":
                kill_signal = getattr(signal, 'SIGKILL', signal.SIGTERM)
            else:
                kill_signal = signal.SIGTERM
            os.kill(current_pid, kill_signal)
            killed_pids.append(current_pid)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    time.sleep(1)
    return jsonify({"success": True, "message": f"Force killed PIDs: {', '.join(map(str, killed_pids))}"})

@bp.route('/metrics', methods=['GET'])
def prometheus_metrics():
    """Prometheus metrics are not implemented."""
    return jsonify({"error": "Prometheus metrics are not enabled"}), 501

@bp.route('/ping', methods=['GET'])
def ping():
    """Lightweight health check for orchestrators (Docker, K8s, load balancers)."""
    return jsonify({'status': 'ok'}), 200


@bp.route('/health', methods=['GET'])
def simple_health():
    """Simple health endpoint for monitoring."""

    try:
        health = main_routes._get_ollama_service().get_component_health()
        if health.get('background_thread_alive'):
            return jsonify({'status': 'ok'}), 200
        else:
            return jsonify({'status': 'degraded'}), 503
    except _ROUTE_ERRORS:
        return jsonify({'status': 'error'}), 500

@bp.route('/admin/model-defaults')
def admin_model_defaults():
    return render_template('admin_model_defaults.html')

