"""WSGI entry point for Waitress, Gunicorn, and other production servers.

Usage:
    waitress-serve --host=127.0.0.1 --port=5000 wsgi:app
    gunicorn --config app/config/gunicorn.py wsgi:app

MCP Streamable HTTP is mounted at /mcp via create_app() (same port).
"""
from app import create_app

app = create_app('production')
