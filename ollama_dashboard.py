"""
Ollama Dashboard application entry point.

This module initializes and runs the Flask application for the Ollama Dashboard,
which provides a web interface for managing Ollama models and services.
"""
import logging

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Suppress routine Flask request logs, only show warnings and errors
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)

    print(" * Starting Ollama Dashboard on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
