"""Unit tests for Ollama connection configuration logic.

Tests _get_ollama_host_port() in isolation — no live Ollama server required.
The old file was a diagnostic script; this replaces it with proper pytest tests.
"""
import os
from unittest.mock import MagicMock, patch

import pytest
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


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()


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

    def test_strips_proxy_url_misconfiguration(self, service_with_app):
        """OLLAMA_HOST=host:port/ollama must not append /ollama to outbound API URLs."""
        service_with_app.app.config['OLLAMA_HOST'] = '127.0.0.1:11436/ollama'
        service_with_app.app.config['OLLAMA_PORT'] = 11434
        host, port = service_with_app._get_ollama_host_port()
        assert host == '127.0.0.1'
        assert port == 11436

    def test_embedded_port_in_host_after_scheme_strip(self, service_with_app):
        service_with_app.app.config['OLLAMA_HOST'] = 'http://127.0.0.1:11436'
        service_with_app.app.config['OLLAMA_PORT'] = 11434
        host, port = service_with_app._get_ollama_host_port()
        assert host == '127.0.0.1'
        assert port == 11436


class TestAppConfig:
    """Verify that create_app() correctly exposes OLLAMA_HOST/PORT."""

    def test_default_host_and_port(self):
        """create_app() should default to localhost:11434 when env does not override."""
        removed = {}
        for key in ('OLLAMA_HOST', 'OLLAMA_PORT'):
            if key in os.environ:
                removed[key] = os.environ.pop(key)
        try:
            app = create_app()
            assert app.config.get('OLLAMA_HOST') == 'localhost'
            assert app.config.get('OLLAMA_PORT') == 11434
        finally:
            os.environ.update(removed)

    def test_env_override(self):
        """create_app() should pick up OLLAMA_HOST/PORT from env vars."""
        with patch.dict(os.environ, {'OLLAMA_HOST': '192.168.1.100', 'OLLAMA_PORT': '11500'}):
            app = create_app()
        assert app.config.get('OLLAMA_HOST') == '192.168.1.100'
        assert app.config.get('OLLAMA_PORT') == 11500


class TestOllamaApiBaseFormatting:
    def test_format_ollama_api_base_includes_scheme(self):
        from app.routes.main import _format_ollama_api_base, _format_ollama_host_port_label

        assert _format_ollama_host_port_label('localhost', 11434) == 'localhost:11434'
        assert _format_ollama_api_base('localhost', 11434) == 'http://localhost:11434'

    def test_format_ollama_api_base_brackets_ipv6(self):
        from app.routes.main import _format_ollama_api_base, _format_ollama_host_port_label

        assert _format_ollama_host_port_label('::1', 11434) == '[::1]:11434'
        assert _format_ollama_api_base('::1', 11434) == 'http://[::1]:11434'

    def test_format_proxy_endpoint_label_strips_scheme(self):
        from app.routes.main import _format_proxy_endpoint_label

        assert _format_proxy_endpoint_label('http://localhost:5000/ollama') == 'localhost:5000/ollama'
        assert _format_proxy_endpoint_label('https://127.0.0.1:5000/ollama') == '127.0.0.1:5000/ollama'
        assert _format_proxy_endpoint_label('localhost:5000/ollama') == 'localhost:5000/ollama'

    def test_index_header_endpoint_display_omits_scheme(self, client):
        """Header chips show host:port (no http://); copy attributes keep full URL."""
        from unittest.mock import patch

        from app.routes import main

        stats = {
            'cpu_percent': 0,
            'memory': {'percent': 0, 'total': 0, 'available': 0, 'used': 0},
            'vram': {'percent': 0, 'total': 0, 'used': 0, 'free': 0, 'gpu_3d': 0},
            'disk': {'percent': 0},
        }
        with patch.object(main.ollama_service, 'is_ollama_installed', return_value=True), patch(
            'app.routes.main.run_startup_ollama_update_check',
            return_value={'update_available': False, 'current_version': '0.17.0'},
        ), patch.object(main.ollama_service, 'get_running_models', return_value=[]), patch.object(
            main.ollama_service, 'get_available_models', return_value=[]
        ), patch.object(main.ollama_service, 'get_system_stats', return_value=stats), patch.object(
            main.ollama_service, 'get_ollama_version', return_value='0.17.0'
        ):
            html = client.get('/').get_data(as_text=True)

        assert 'id="apiProxyEndpoint"' in html
        assert 'data-copy-value="http://localhost/ollama"' in html or '/ollama"' in html
        assert '>localhost' in html or '>127.0.0.1' in html
        proxy_start = html.find('id="apiProxyEndpoint"')
        proxy_tag = html[proxy_start : html.find('</code>', proxy_start)]
        assert 'http://' not in proxy_tag.split('>', 1)[-1]
        assert 'data-copy-value="http://' in html
        assert 'localhost:11434' in html

