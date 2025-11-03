"""
Flask application factory for Ollama Dashboard.
"""
import os
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
import pytz


class Config:
    """Application configuration settings."""
    OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'localhost')
    OLLAMA_PORT = int(os.getenv('OLLAMA_PORT', 11434))
    MAX_HISTORY = int(os.getenv('MAX_HISTORY', 50))
    HISTORY_FILE = os.getenv('HISTORY_FILE', 'history.json')
    STATIC_URL_PATH = ''
    STATIC_FOLDER = 'static'
    TEMPLATE_FOLDER = 'templates'


def create_app():
    """
    Application factory function.

    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__,
                static_url_path=Config.STATIC_URL_PATH,
                static_folder=Config.STATIC_FOLDER,
                template_folder=Config.TEMPLATE_FOLDER)

    # Load configuration
    app.config.from_object(Config)

    # Configure CORS
    CORS(app, resources={
        r"/*": {
            "origins": "*",
            "allow_headers": "*",
            "expose_headers": "*"
        }
    })

    # Register template filters
    _register_template_filters(app)

    # Register blueprints
    _register_blueprints(app)

    # Register error handlers
    _register_error_handlers(app)

    # Health check endpoint
    @app.route('/ping')
    def ping():
        """Health check endpoint."""
        return jsonify({"status": "ok"})

    return app


def _register_template_filters(app):
    """Register custom Jinja2 template filters."""
    @app.template_filter('datetime')
    def format_datetime(value):
        """Format datetime value for display."""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00').split('.')[0])
            except ValueError:
                return value
        return value.strftime('%Y-%m-%d %H:%M:%S')

    @app.template_filter('time_ago')
    def time_ago(value):
        """Convert datetime to relative time string."""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00').split('.')[0])
            except ValueError:
                return value

        now = datetime.now(pytz.UTC)
        if isinstance(value, datetime):
            value = value.replace(tzinfo=pytz.UTC)

        diff = now - value
        seconds = diff.total_seconds()

        if seconds < 60:
            return f"{int(seconds)} seconds ago"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"


def _register_blueprints(app):
    """Register Flask blueprints."""
    from app.routes import bp as main_bp
    from app.routes.main import init_app as init_main_bp

    app.register_blueprint(main_bp)
    init_main_bp(app)


def _register_error_handlers(app):
    """Register error handlers."""
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors."""
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        return jsonify({"error": "Internal server error"}), 500
