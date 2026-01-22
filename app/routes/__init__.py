"""Routes package initialization."""

# This file makes the routes directory a Python package

from flask import Blueprint

bp = Blueprint('main', __name__)

from . import main  # Import views
from .main import init_app  # Import init function