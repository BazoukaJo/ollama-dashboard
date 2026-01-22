"""Flask application factory for Ollama Dashboard.

Initializes Flask app with configuration, services, and route blueprints.
Single initialization point - ensures no duplicate service creation.
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask
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
    app = Flask(
        __name__,
        static_folder='static',
        static_url_path='/static',
        template_folder='templates'
    )

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

    logger.info(f"🔧 Configuring Ollama Dashboard in {config_name} mode")
    logger.info(f"📁 Data directory: {app.config['DATA_DIR']}")

    # ===== SERVICE INITIALIZATION =====
    from app.services.ollama import OllamaService

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

    # ===== MIDDLEWARE & SECURITY =====

    # CORS: Allow requests from local interfaces
    cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000')
    CORS(app, resources={r"/api/*": {"origins": cors_origins.split(',')}})

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if os.getenv('HTTPS_ENABLED', 'false').lower() == 'true':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # ===== BLUEPRINT REGISTRATION =====

    # Single initialization path for all routes
    from app.routes import init_app

    init_app(app)
    logger.info("✅ Routes registered (47 endpoints)")


    logger.info("✅ Application initialized successfully")
    return app
