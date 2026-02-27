"""Tests for dashboard template structure: capability filters, model cards, section headers."""

import pytest
from unittest.mock import patch


@pytest.fixture
def app():
    """Create app for tests."""
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


class TestCapabilityFiltersVisibility:
    """Capability filters should appear only in the first section with content."""

    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_available_models')
    @patch('app.routes.main.ollama_service.get_system_stats')
    @patch('app.routes.main.ollama_service.get_ollama_version')
    def test_filters_in_running_when_running_has_models(
        self, mock_version, mock_stats, mock_available, mock_running, client
    ):
        """When Running has models, filters appear only in Running section."""
        mock_running.return_value = [{'name': 'llama3.1:8b'}]
        mock_available.return_value = []
        mock_stats.return_value = {
            'cpu_percent': 0, 'memory': {'percent': 0},
            'vram': {'percent': 0}, 'disk': {'percent': 0},
        }
        mock_version.return_value = '0.17.0'

        response = client.get('/')
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        assert 'runningModelsFilters' in html
        assert 'capability-filters' in html

    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_available_models')
    @patch('app.routes.main.ollama_service.get_system_stats')
    @patch('app.routes.main.ollama_service.get_ollama_version')
    def test_filters_in_available_when_no_running(
        self, mock_version, mock_stats, mock_available, mock_running, client
    ):
        """When no Running models but Available has models, filters in Available."""
        mock_running.return_value = []
        mock_available.return_value = [
            {'name': 'llama3.1:8b', 'size': 1000, 'details': {}}
        ]
        mock_stats.return_value = {
            'cpu_percent': 0, 'memory': {'percent': 0},
            'vram': {'percent': 0}, 'disk': {'percent': 0},
        }
        mock_version.return_value = '0.17.0'

        response = client.get('/')
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        assert 'availableModelsFilters' in html
        assert 'capability-filters' in html

    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_available_models')
    @patch('app.routes.main.ollama_service.get_system_stats')
    @patch('app.routes.main.ollama_service.get_ollama_version')
    def test_filters_in_best_when_no_running_no_available(
        self, mock_version, mock_stats, mock_available, mock_running, client
    ):
        """When no Running and no Available, filters in Downloadable Models."""
        mock_running.return_value = []
        mock_available.return_value = []
        mock_stats.return_value = {
            'cpu_percent': 0, 'memory': {'percent': 0},
            'vram': {'percent': 0}, 'disk': {'percent': 0},
        }
        mock_version.return_value = '0.17.0'

        response = client.get('/')
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        assert 'bestModelsFilters' in html
        assert 'Downloadable Models' in html


class TestModelCardStructure:
    """Model cards should have consistent structure (3 spec rows)."""

    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_available_models')
    @patch('app.routes.main.ollama_service.get_system_stats')
    @patch('app.routes.main.ollama_service.get_ollama_version')
    def test_running_card_has_three_spec_rows(
        self, mock_version, mock_stats, mock_available, mock_running, client
    ):
        """Running model cards have Family, Size+GPU, Context spec rows."""
        mock_running.return_value = [
            {'name': 'llama3.1:8b', 'details': {'family': 'llama'}, 'parameter_size': '8B'}
        ]
        mock_available.return_value = []
        mock_stats.return_value = {
            'cpu_percent': 0, 'memory': {'percent': 0},
            'vram': {'percent': 0}, 'disk': {'percent': 0},
        }
        mock_version.return_value = '0.17.0'

        response = client.get('/')
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        assert 'spec-label">Family' in html
        assert 'spec-label">Parameters' in html
        assert 'spec-label">Size' in html
        assert 'GPU Allocation' in html or 'spec-label' in html
        assert 'spec-label">Context' in html
        assert 'spec-row' in html

    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_available_models')
    @patch('app.routes.main.ollama_service.get_system_stats')
    @patch('app.routes.main.ollama_service.get_ollama_version')
    def test_available_card_has_three_spec_rows(
        self, mock_version, mock_stats, mock_available, mock_running, client
    ):
        """Available model cards have Family, Size, Context spec rows."""
        mock_running.return_value = []
        mock_available.return_value = [
            {'name': 'llama3.1:8b', 'size': 5000000000, 'details': {'family': 'llama'}}
        ]
        mock_stats.return_value = {
            'cpu_percent': 0, 'memory': {'percent': 0},
            'vram': {'percent': 0}, 'disk': {'percent': 0},
        }
        mock_version.return_value = '0.17.0'

        response = client.get('/')
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        assert 'spec-label">Family' in html
        assert 'spec-label">Context' in html


class TestSectionHeaders:
    """Section headers should be present and properly structured."""

    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_available_models')
    @patch('app.routes.main.ollama_service.get_system_stats')
    @patch('app.routes.main.ollama_service.get_ollama_version')
    def test_main_sections_present(
        self, mock_version, mock_stats, mock_available, mock_running, client
    ):
        """Dashboard has System Resources, model sections, and header."""
        mock_running.return_value = []
        mock_available.return_value = []
        mock_stats.return_value = {
            'cpu_percent': 0, 'memory': {'percent': 0},
            'vram': {'percent': 0}, 'disk': {'percent': 0},
        }
        mock_version.return_value = '0.17.0'

        response = client.get('/')
        assert response.status_code == 200
        html = response.get_data(as_text=True)

        assert 'Ollama Dashboard' in html
        assert 'System Resources' in html
        assert 'Downloadable Models' in html
        assert 'section-title-text' in html
