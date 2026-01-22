"""Authentication and authorization service for Ollama Dashboard.

Provides:
- API key generation and validation
- Role-based access control (RBAC)
- Audit logging of authentication events
- Stateless token verification
"""

import os
import secrets
import logging
from functools import wraps
from typing import Optional, Dict, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class AuthService:
    """Handles authentication and authorization for the dashboard.

    Uses API keys for authentication:
    - API_KEY_VIEWER: Read-only access
    - API_KEY_OPERATOR: Read + write (start/stop models)
    - API_KEY_ADMIN: Full access (delete, service control, etc.)

    Keys stored in environment variables.
    """

    # Role definitions and their permissions
    ROLES = {
        'viewer': ['GET'],
        'operator': ['GET', 'POST'],
        'admin': ['GET', 'POST', 'PUT', 'DELETE'],
    }

    # Routes that require admin role
    ADMIN_ONLY = [
        '/api/service/stop',
        '/api/service/start',
        '/api/service/restart',
        '/api/full/restart',
        '/api/force_kill',
        '/api/reload_app',
        '/api/models/delete',
        '/admin/model-defaults',
    ]

    # Routes that require at least operator role
    OPERATOR_ONLY = [
        '/api/models/start',
        '/api/models/stop',
        '/api/models/restart',
        '/api/models/pull',
        '/api/models/settings',
        '/api/chat',
    ]

    def __init__(self):
        """Initialize authentication service."""
        self.audit_log_file = os.getenv('AUDIT_LOG_FILE', 'logs/audit.log')
        self._ensure_audit_log_dir()

        # Load API keys from environment
        self.api_keys = {
            'viewer': os.getenv('API_KEY_VIEWER', self._generate_default_key('viewer')),
            'operator': os.getenv('API_KEY_OPERATOR', self._generate_default_key('operator')),
            'admin': os.getenv('API_KEY_ADMIN', self._generate_default_key('admin')),
        }

        logger.info("🔐 AuthService initialized")

    def _ensure_audit_log_dir(self) -> None:
        """Ensure audit log directory exists."""
        log_dir = os.path.dirname(self.audit_log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    @staticmethod
    def _generate_default_key(role: str) -> str:
        """Generate a default API key for a role.

        In production, users should set these via environment variables.
        """
        return f"sk-{role}-{secrets.token_hex(16)}"

    def get_role_from_key(self, api_key: str) -> Optional[str]:
        """Determine role from API key.

        Args:
            api_key: API key to check

        Returns:
            Role name ('viewer', 'operator', 'admin') or None if invalid
        """
        for role, key in self.api_keys.items():
            if key == api_key:
                return role
        return None

    def authenticate_request(self, request) -> Tuple[bool, Optional[str]]:
        """Authenticate HTTP request.

        Checks for API key in:
        1. Authorization header: Bearer <key>
        2. Query parameter: ?api_key=<key>

        Args:
            request: Flask request object

        Returns:
            Tuple of (is_authenticated, role_name)
        """
        # Get API key from header or query parameter
        auth_header = request.headers.get('Authorization', '')
        api_key = None

        if auth_header.startswith('Bearer '):
            api_key = auth_header[7:].strip()
        else:
            api_key = request.args.get('api_key') or request.form.get('api_key')

        if not api_key:
            self._audit_log('AUTH_MISSING', request)
            return False, None

        role = self.get_role_from_key(api_key)
        if role:
            self._audit_log('AUTH_SUCCESS', request, role)
            return True, role
        else:
            self._audit_log('AUTH_FAILED', request)
            return False, None

    def check_permission(self, request, role: str, endpoint: str, method: str) -> bool:
        """Check if authenticated role can access endpoint.

        Args:
            request: Flask request object
            role: User's role ('viewer', 'operator', 'admin')
            endpoint: API endpoint path
            method: HTTP method (GET, POST, DELETE, etc.)

        Returns:
            True if access allowed, False otherwise
        """
        # Admin has access to everything
        if role == 'admin':
            return True

        # Check admin-only endpoints
        if any(endpoint.startswith(path) for path in self.ADMIN_ONLY):
            self._audit_log('AUTH_DENIED_ADMIN_ONLY', request, role, endpoint)
            return False

        # Check operator-only endpoints
        if any(endpoint.startswith(path) for path in self.OPERATOR_ONLY):
            if role == 'viewer':
                self._audit_log('AUTH_DENIED_OPERATOR_ONLY', request, role, endpoint)
                return False

        return True

    def _audit_log(self, event: str, request, role: Optional[str] = None, endpoint: str = None) -> None:
        """Log authentication event for audit trail.

        Args:
            event: Event type (AUTH_SUCCESS, AUTH_FAILED, AUTH_DENIED_*, etc.)
            request: Flask request object
            role: User's role (if authenticated)
            endpoint: API endpoint being accessed
        """
        try:
            timestamp = datetime.now().isoformat()
            ip_addr = request.remote_addr or 'unknown'
            user_agent = request.headers.get('User-Agent', 'unknown')[:100]

            log_entry = {
                'timestamp': timestamp,
                'event': event,
                'ip': ip_addr,
                'role': role or 'none',
                'endpoint': endpoint or request.path,
                'method': request.method,
                'user_agent': user_agent,
            }

            # Write to audit log (append-only)
            with open(self.audit_log_file, 'a', encoding='utf-8') as f:
                import json
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")


def require_auth(f):
    """Decorator to require authentication on a route.

    Usage:
        @app.route('/api/admin')
        @require_auth
        def admin_endpoint():
            return {"message": "admin only"}
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request, jsonify
        from app import current_app

        auth_service = current_app.config.get('AUTH_SERVICE')
        if not auth_service:
            return {"error": "Auth service not configured"}, 500

        is_authenticated, role = auth_service.authenticate_request(request)
        if not is_authenticated:
            return {"error": "Unauthorized"}, 401

        # Store role in kwargs for endpoint to use
        kwargs['_auth_role'] = role
        return f(*args, **kwargs)

    return decorated_function


def require_role(required_role: str):
    """Decorator to require specific role on a route.

    Usage:
        @app.route('/api/admin')
        @require_role('admin')
        def admin_endpoint():
            return {"message": "admin only"}
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request, jsonify
            from app import current_app

            auth_service = current_app.config.get('AUTH_SERVICE')
            if not auth_service:
                return {"error": "Auth service not configured"}, 500

            is_authenticated, role = auth_service.authenticate_request(request)
            if not is_authenticated:
                return {"error": "Unauthorized"}, 401

            # Check role requirement
            role_hierarchy = {'viewer': 1, 'operator': 2, 'admin': 3}
            required_level = role_hierarchy.get(required_role, 0)
            user_level = role_hierarchy.get(role, 0)

            if user_level < required_level:
                auth_service._audit_log('AUTH_DENIED_ROLE', request, role, request.path)
                return {"error": f"Requires {required_role} role or higher"}, 403

            kwargs['_auth_role'] = role
            return f(*args, **kwargs)

        return decorated_function
    return decorator
