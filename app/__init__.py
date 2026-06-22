"""Flask application factory for Ollama Dashboard.

Initializes Flask app with configuration, services, and route blueprints.
Single initialization point - ensures no duplicate service creation.
"""

__version__ = "1.2.0"

import html
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

logger = logging.getLogger(__name__)


def _migrate_legacy_root_data_files(base_dir: Path, data_dir: Path) -> None:
    """Move persistence JSON from repo root into data/ (one-time, best-effort)."""
    for name in (
        'history.json',
        'chat_history.json',
        'model_settings.json',
        'system_stats_history.json',
    ):
        legacy = base_dir / name
        dest = data_dir / name
        if legacy.is_file() and not dest.exists():
            try:
                shutil.move(str(legacy), str(dest))
                logger.info("Migrated legacy data file %s -> %s", name, dest)
            except OSError as exc:
                logger.warning("Could not migrate %s: %s", name, exc)


def _schedule_startup_prewarm(app, ollama_service) -> None:
    """Pre-load the configured default IDE model so the first Copilot turn is not a cold start.

    Opt-in via ``COPILOT_PREWARM_MODEL`` (gated by ``COPILOT_PREWARM_ON_START``, default on); a
    no-op when unset so existing setups are unaffected. Fully best-effort: any failure is logged
    and never blocks or crashes startup.
    """
    model_name = os.getenv('COPILOT_PREWARM_MODEL', '').strip()
    if not model_name:
        return
    try:
        from app.services.model_residency import parse_residency_env, _env_bool as residency_env_bool

        if residency_env_bool('RESIDENCY_ON_START', True):
            residency_models = {s.model for s in parse_residency_env()}
            if model_name in residency_models:
                logger.info(
                    "Skipping startup prewarm for %s (handled by residency pins)",
                    model_name,
                )
                return
    except Exception:  # noqa: BLE001 - skip check is best-effort
        pass
    try:
        from app.services.copilot_prewarm import schedule_startup_prewarm
        from app.services.model_settings_helpers import (
            compute_fresh_recommended_settings_entry,
            lookup_settings_entry,
        )
        from app.services.settings_cache import load_settings_file

        entry = None
        try:
            entry = lookup_settings_entry(
                load_settings_file(Path(app.config['MODEL_SETTINGS_FILE'])), model_name,
            )
        except (OSError, ValueError):
            entry = None
        if not entry:
            with app.app_context():
                try:
                    entry = compute_fresh_recommended_settings_entry(ollama_service, model_name)
                except Exception:  # noqa: BLE001 - recommendation is best-effort
                    entry = None
        options = (entry or {}).get('settings') or {}
        host = app.config['OLLAMA_HOST']
        port = app.config['OLLAMA_PORT']
        schedule_startup_prewarm(f'http://{host}:{port}', model_name, options)
        logger.info("🔥 Scheduled startup prewarm for %s", model_name)
    except Exception as err:  # noqa: BLE001 - prewarm must never break startup
        logger.warning("Startup prewarm skipped: %s", err)


def _schedule_startup_residency(app, ollama_service) -> None:
    """Pin fast + heavy models in Ollama RAM (best-effort, non-blocking)."""
    try:
        from app.services.model_residency import startup_residency_from_env

        startup_residency_from_env(app, ollama_service)
    except Exception as err:  # noqa: BLE001 - residency must never break startup
        logger.warning("Startup residency skipped: %s", err)


def create_app(config_name='development'):
    """Create and configure Flask application.

    Args:
        config_name: Configuration mode ('development' or 'production')

    Returns:
        Configured Flask application instance

    Notes:
        - Initializes single OllamaService instance
        - Registers blueprints and middleware
        - Sets up CORS and security headers
    """
    env_config = os.getenv('OLLAMA_DASHBOARD_CONFIG', '').strip().lower()
    if env_config in ('development', 'production'):
        config_name = env_config

    base_dir = Path(__file__).parent.parent
    load_dotenv(base_dir / '.env', override=False)

    _log_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    _log_level = getattr(logging, _log_name, logging.INFO)
    if isinstance(_log_level, int):
        logging.getLogger().setLevel(_log_level)

    app = Flask(
        __name__,
        static_folder='static',
        static_url_path='/static',
        template_folder='templates'
    )

    from app.services.model_helpers import (  # pylint: disable=import-outside-toplevel
        format_context_length,
        resolve_quantization_level,
    )

    @app.template_filter('format_context_length')
    def _format_context_length_filter(value):
        if value is None:
            return '—'
        formatted = format_context_length(value)
        if formatted is not None:
            return formatted
        return value if isinstance(value, str) and value.strip() else '—'

    @app.template_filter('model_quantization_label')
    def _model_quantization_label(model):
        if not isinstance(model, dict):
            return '—'
        quant = resolve_quantization_level(model)
        return quant if quant else '—'

    app.config['START_TIME'] = datetime.now(timezone.utc)

    app.config['DEBUG'] = config_name == 'development'
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

    # Data directory for history, settings, cache
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data'
    data_dir.mkdir(exist_ok=True)
    _migrate_legacy_root_data_files(base_dir, data_dir)
    app.config['DATA_DIR'] = str(data_dir)

    app.config['OLLAMA_HOST'] = os.getenv('OLLAMA_HOST', 'localhost')
    app.config['OLLAMA_PORT'] = int(os.getenv('OLLAMA_PORT', '11434'))
    app.config['AUTO_START_OLLAMA'] = os.getenv('AUTO_START_OLLAMA', 'true').lower() in ('true', '1', 'yes', 'on')

    app.config['HISTORY_FILE'] = os.getenv('HISTORY_FILE', str(data_dir / 'history.json'))
    app.config['MODEL_SETTINGS_FILE'] = os.getenv(
        'MODEL_SETTINGS_FILE', str(data_dir / 'model_settings.json')
    )
    app.config['MAX_HISTORY'] = int(os.getenv('MAX_HISTORY', '50'))

    logger.info("🔧 Configuring Ollama Dashboard in %s mode", config_name)
    logger.info("📁 Data directory: %s", app.config['DATA_DIR'])

    from app.services.ollama import OllamaService  # pylint: disable=import-outside-toplevel

    ollama_service = OllamaService()
    app.config['OLLAMA_SERVICE'] = ollama_service

    with app.app_context():
        ollama_service.init_app(app)

    logger.info("✅ OllamaService initialized")

    enable_auth = os.getenv('ENABLE_AUTH', 'false').lower() in ('true', '1', 'yes')
    if enable_auth:
        from app.services.auth import AuthService  # pylint: disable=import-outside-toplevel
        auth_service = AuthService()
        app.config['AUTH_SERVICE'] = auth_service

        @app.before_request
        def check_auth():
            path = request.path
            auth_svc = app.config.get('AUTH_SERVICE')
            if not auth_svc:
                return None
            if any(path.startswith(p) for p in auth_svc.ADMIN_ONLY):
                ok, role = auth_svc.authenticate_request(request)
                if not ok:
                    return jsonify({"error": "Unauthorized"}), 401
                if not auth_svc.check_permission(request, role, path, request.method):
                    return jsonify({"error": "Forbidden"}), 403
            elif any(path.startswith(p) for p in auth_svc.OPERATOR_ONLY):
                ok, role = auth_svc.authenticate_request(request)
                if not ok:
                    return jsonify({"error": "Unauthorized"}), 401
                if not auth_svc.check_permission(request, role, path, request.method):
                    return jsonify({"error": "Forbidden"}), 403
            return None

        logger.info("🔐 Auth enabled (admin/operator routes protected)")

    @app.errorhandler(404)
    def not_found(e):
        from flask import request as _req  # pylint: disable=import-outside-toplevel
        # /ollama/* includes the OpenAI-compatible /ollama/v1/* paths VS Code Copilot calls —
        # they must get JSON (not HTML) so OpenAI SDK error parsing works.
        if _req.path.startswith('/api/') or _req.path.startswith('/ollama/'):
            return jsonify({"success": False, "error": "Not found", "message": "Not found"}), 404
        desc = getattr(e, 'description', None) or str(e) or 'Not Found'
        body = (
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Not Found</title></head>'
            f'<body><h1>Not Found</h1><p>{html.escape(str(desc))}</p></body></html>'
        )
        return body, 404, {'Content-Type': 'text/html; charset=utf-8'}

    @app.errorhandler(500)
    def internal_error(e):
        from flask import request as _req  # pylint: disable=import-outside-toplevel
        logger.exception("Unhandled 500 error on %s", _req.path)
        if _req.path.startswith('/api/') or _req.path.startswith('/ollama/'):
            return jsonify({"success": False, "error": "Internal server error",
                            "message": "An internal error occurred."}), 500
        msg = getattr(e, 'description', None) or str(e) or 'Internal Server Error'
        body = (
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Server Error</title></head>'
            f'<body><h1>Internal Server Error</h1><p>{html.escape(str(msg))}</p></body></html>'
        )
        return body, 500, {'Content-Type': 'text/html; charset=utf-8'}

    cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000')
    CORS(app, resources={
        r"/api/*": {"origins": cors_origins.split(',')},
        r"/ollama/*": {"origins": "*"},
        r"/mcp/*": {"origins": "*"},
    })

    @app.after_request
    def set_security_headers(response):
        from app.wsgi_safe import strip_hop_by_hop_headers

        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if os.getenv('HTTPS_ENABLED', 'false').lower() == 'true':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return strip_hop_by_hop_headers(response)

    from app.routes import init_app  # pylint: disable=import-outside-toplevel

    init_app(app)
    logger.info("✅ Routes registered")

    from app.services.mcp_server import mount_mcp_on_flask_app  # pylint: disable=import-outside-toplevel
    mount_mcp_on_flask_app(app)

    _schedule_startup_prewarm(app, ollama_service)
    _schedule_startup_residency(app, ollama_service)

    logger.info("✅ Application initialized successfully")
    return app
