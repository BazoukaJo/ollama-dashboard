"""Shared exception tuples for resilient service and route handlers."""
from __future__ import annotations

import requests

SERVICE_ERRORS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

HTTP_SERVICE_ERRORS = SERVICE_ERRORS + (requests.RequestException,)
