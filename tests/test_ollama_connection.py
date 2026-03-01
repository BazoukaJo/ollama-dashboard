"""Unit tests for Ollama connection configuration logic.

Tests _get_ollama_host_port() in isolation — no live Ollama server required.
The old file was a diagnostic script; this replaces it with proper pytest tests.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.services.ollama_core import OllamaServiceCore


@pytest.fixture(scope="module")
def service_with_app():
    """Return a fully initialised OllamaServiceCore instance."""
    from app.services.ollama import OllamaService
    app = create_app()
    svc = OllamaService()
    with app.app_context():
        svc.app = app
    return svc


class TestGetOllamaHostPort:
    """Unit-test _get_ollama_host_port() in every config scenario."""

    def test_reads_from_app_config(self, service_with_app):
        """Should return the host/port configured in the Flask app."""
        service_with_app.app.config['OLLAMA_HOST'] = 'my-ollama-host'
        service_with_app.app.config['OLLAMA_PORT'] = 12345
        host, port = service_with_app._get_ollama_host_port()
        assert host == 'my-ollama-host'
        assert port == 12345

    def test_falls_back_to_env_when_config_empty(self):
        """Falls back to OLLAMA_HOST / OLLAMA_PORT env vars when app config is blank."""
        core = OllamaServiceCore.__new__(OllamaServiceCore)
        core.app = None
        core.__dict__['logger'] = MagicMock()
        with patch.dict(os.environ, {'OLLAMA_HOST': 'env-host', 'OLLAMA_PORT': '9999'}):
            host, port = core._get_ollama_host_port()
        assert host == 'env-host'
        assert port == 9999

    def test_defaults_when_no_config_no_env(self):
        """Defaults to localhost:11434 when neither app config nor env vars are set."""
        core = OllamaServiceCore.__new__(OllamaServiceCore)
        core.app = None
        core.__dict__['logger'] = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            # Remove relevant keys if present
            for k in ('OLLAMA_HOST', 'OLLAMA_PORT'):
                os.environ.pop(k, None)
            host, port = core._get_ollama_host_port()
        assert host == 'localhost'
        assert port == 11434

    def test_invalid_port_string_falls_back(self):
        """Non-numeric port in env falls back to 11434."""
        core = OllamaServiceCore.__new__(OllamaServiceCore)
        core.app = None
        core.__dict__['logger'] = MagicMock()
        with patch.dict(os.environ, {'OLLAMA_HOST': 'localhost', 'OLLAMA_PORT': 'not-a-number'}):
            host, port = core._get_ollama_host_port()
        assert port == 11434

    def test_port_out_of_range_falls_back(self, service_with_app):
        """Port outside 1-65535 is rejected and replaced with 11434."""
        service_with_app.app.config['OLLAMA_HOST'] = 'localhost'
        service_with_app.app.config['OLLAMA_PORT'] = 99999
        _, port = service_with_app._get_ollama_host_port()
        assert port == 11434

    def test_public_alias_matches(self, service_with_app):
        """get_ollama_host_port() is just an alias for _get_ollama_host_port()."""
        service_with_app.app.config['OLLAMA_HOST'] = 'localhost'
        service_with_app.app.config['OLLAMA_PORT'] = 11434
        assert service_with_app.get_ollama_host_port() == service_with_app._get_ollama_host_port()


class TestAppConfig:
    """Verify that create_app() correctly exposes OLLAMA_HOST/PORT."""

    def test_default_host_and_port(self):
        """create_app() should default to localhost:11434."""
        app = create_app()
        assert app.config.get('OLLAMA_HOST') == 'localhost'
        assert app.config.get('OLLAMA_PORT') == 11434

    def test_env_override(self):
        """create_app() should pick up OLLAMA_HOST/PORT from env vars."""
        with patch.dict(os.environ, {'OLLAMA_HOST': '192.168.1.100', 'OLLAMA_PORT': '11500'}):
            app = create_app()
        assert app.config.get('OLLAMA_HOST') == '192.168.1.100'
        assert app.config.get('OLLAMA_PORT') == 11500


