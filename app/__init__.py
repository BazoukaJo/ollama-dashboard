"""Flask application factory for Ollama Dashboard.

Initializes Flask app with configuration, services, and route blueprints.
Single initialization point - ensures no duplicate service creation.
"""

__version__ = "1.1.0"

import html
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

logger = logging.getLogger(__name__)


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

    # Record exact startup time so get_component_health() can report accurate uptime
    app.config['START_TIME'] = datetime.now(timezone.utc)

    # ===== CONFIGURATION =====
    app.config['DEBUG'] = config_name == 'development'
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

    # Data directory for history, settings, cache
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data'
    data_dir.mkdir(exist_ok=True)
    app.config['DATA_DIR'] = str(data_dir)

    # Ollama connection
    app.config['OLLAMA_HOST'] = os.getenv('OLLAMA_HOST', 'localhost')
    app.config['OLLAMA_PORT'] = int(os.getenv('OLLAMA_PORT', '11434'))

    # Persistence
    app.config['HISTORY_FILE'] = os.getenv('HISTORY_FILE', 'history.json')
    app.config['MODEL_SETTINGS_FILE'] = os.getenv('MODEL_SETTINGS_FILE', 'model_settings.json')
    app.config['MAX_HISTORY'] = int(os.getenv('MAX_HISTORY', '50'))

    logger.info("🔧 Configuring Ollama Dashboard in %s mode", config_name)
    logger.info("📁 Data directory: %s", app.config['DATA_DIR'])

    # ===== SERVICE INITIALIZATION =====
    from app.services.ollama import OllamaService  # pylint: disable=import-outside-toplevel

    # Create single service instance
    ollama_service = OllamaService()
    app.config['OLLAMA_SERVICE'] = ollama_service

    # Initialize service with Flask app context
    with app.app_context():
        ollama_service.init_app(app)

    logger.info("✅ OllamaService initialized")
    logger.info("   • Error handling (20+ pattern detection)")
    logger.info("   • Smart caching (2s-300s TTLs)")
    logger.info("   • Rate limiting (3 operation types)")
    logger.info("   • Performance monitoring")
    logger.info("   • Health tracking")

    # ===== AUTHENTICATION (optional) =====
    enable_auth = os.getenv('ENABLE_AUTH', 'false').lower() in ('true', '1', 'yes')
    if enable_auth:
        from app.services.auth import AuthService  # pylint: disable=import-outside-toplevel
        auth_service = AuthService()
        app.config['AUTH_SERVICE'] = auth_service

        @app.before_request
        def check_auth():
            from flask import jsonify, request  # pylint: disable=import-outside-toplevel
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

    # ===== ERROR HANDLERS =====
    @app.errorhandler(404)
    def not_found(e):
        from flask import request as _req  # pylint: disable=import-outside-toplevel
        if _req.path.startswith('/api/') or _req.path.startswith('/ollama/api/'):
            return jsonify({"success": False, "error": "Not found", "message": str(e)}), 404
        desc = getattr(e, 'description', None) or str(e) or 'Not Found'
        body = (
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Not Found</title></head>'
            f'<body><h1>Not Found</h1><p>{html.escape(str(desc))}</p></body></html>'
        )
        return body, 404, {'Content-Type': 'text/html; charset=utf-8'}

    @app.errorhandler(500)
    def internal_error(e):
        from flask import request as _req  # pylint: disable=import-outside-toplevel
        if _req.path.startswith('/api/') or _req.path.startswith('/ollama/api/'):
            return jsonify({"success": False, "error": "Internal server error", "message": str(e)}), 500
        msg = getattr(e, 'description', None) or str(e) or 'Internal Server Error'
        body = (
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Server Error</title></head>'
            f'<body><h1>Internal Server Error</h1><p>{html.escape(str(msg))}</p></body></html>'
        )
        return body, 500, {'Content-Type': 'text/html; charset=utf-8'}

    # ===== MIDDLEWARE & SECURITY =====
    cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000')
    # Updated CORS rule to grant full API clearance to the dashboard and external IDE connections
    CORS(app, resources={r"/api/*": {"origins": cors_origins.split(',')}, r"/ollama/*": {"origins": "*"}})

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if os.getenv('HTTPS_ENABLED', 'false').lower() == 'true':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # ===== INJECTED OLLAMA PARAMETER INTERCEPTOR PROXY =====
    import json
    import requests
    from flask import request, Response, stream_with_context

    settings_path = Path(app.config['DATA_DIR']) / app.config['MODEL_SETTINGS_FILE']
    ollama_url = f"http://{app.config['OLLAMA_HOST']}:{app.config['OLLAMA_PORT']}"

    @app.route('/ollama/api/chat', methods=['POST'])
    @app.route('/ollama/api/generate', methods=['POST'])
    def intercept_ollama_parameters():
        """Hijacks VS Code request payloads to force dashboard parameters."""
        payload = request.get_json(silent=True) or {}
        model_name = payload.get("model")
        incoming_options = payload.get("options", {})

        dashboard_options = {}
        if settings_path.exists():
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    all_settings = json.load(f)
                    dashboard_options = all_settings.get(model_name, {})
            except Exception as proxy_err:
                logger.error("Proxy failed reading settings database: %s", proxy_err)

        # Merge options dictionary: Dashboard choices completely override extension defaults
        payload["options"] = {**incoming_options, **dashboard_options}

        def stream_response_tokens():
            upstream = requests.post(
                f"{ollama_url}/api/{request.path.split('/')[-1]}",
                json=payload,
                stream=True
            )
            for token_chunk in upstream.iter_content(chunk_size=1024):
                if token_chunk:
                    yield token_chunk

        return Response(stream_with_context(stream_response_tokens()), content_type='application/json')

    @app.route('/ollama/api/<path:catchall>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
    def proxy_general_ollama_calls(catchall):
        """Passes model tags, pull actions, and metadata through safely to Ollama."""
        if request.method == 'OPTIONS':
            res = Response()
            res.headers['Access-Control-Allow-Origin'] = '*'
            res.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            res.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return res

        forward_headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
        target_endpoint = f"{ollama_url}/api/{catchall}"

        response_data = requests.request(
            method=request.method,
            url=target_endpoint,
            headers=forward_headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False
        )

        proxy_response = Response(
            response_data.content,
            response_data.status_code,
            list(response_data.headers.items())
        )
        proxy_response.headers['Access-Control-Allow-Origin'] = '*'
        return proxy_response

    # ===== BLUEPRINT REGISTRATION =====
    from app.routes import init_app  # pylint: disable=import-outside-toplevel

    init_app(app)
    logger.info("✅ Routes registered (47 endpoints)")

    logger.info("✅ Application initialized successfully")
    return app
