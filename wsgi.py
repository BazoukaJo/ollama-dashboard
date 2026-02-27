"""WSGI entry point for Gunicorn and other production servers.

Usage:
    gunicorn --config app/config/gunicorn.py wsgi:app
"""
from app import create_app

app = create_app()
