from app import create_app

# WSGI entry point for the ollama-dashboard application.
#
# This module provides the WSGI application entry point for the ollama-dashboard
# Flask application. It can be used to run the development server or deploy
# the application using a WSGI server like Gunicorn.
#
# Example:
#     To run the development server:
#         python wsgi.py
#
#     To deploy with Gunicorn:
#         gunicorn wsgi:app
#

app = create_app()

if __name__ == '__main__':
    # Run development server as a convenience wrapper
    app.run(host='0.0.0.0', port=5000)
