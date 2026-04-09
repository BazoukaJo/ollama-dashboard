"""Routes package initialization."""

# This file makes the routes directory a Python package

from flask import Blueprint

bp = Blueprint('main', __name__)

from . import main as main  # noqa: E402 — side effect: registers routes on bp
from .main import init_app as init_app  # noqa: E402

__all__ = ['bp', 'init_app', 'main']
