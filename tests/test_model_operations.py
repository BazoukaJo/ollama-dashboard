"""
Comprehensive tests for model operations: start, stop, restart, delete.
Tests cover success paths, error handling, and edge cases.
"""

import pytest
from unittest.mock import Mock, patch
import requests
from app import create_app


@pytest.fixture
def app():
    """Create and configure a test Flask app."""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create a test client for the Flask app."""
    return app.test_client()


class TestModelStop:
    """Test suite for model stop endpoint."""

    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_stop_model_success(self, mock_status, mock_running, mock_post, client):
        """Test successfully stopping a running model."""
        mock_status.return_value = True
        mock_running.return_value = [{'name': 'llama2:latest', 'size': 1000000}]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'success'}
        mock_post.return_value = mock_response

        response = client.post('/api/models/stop/llama2:latest')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'stopped successfully' in data['message'].lower()

        # Verify the correct API call was made
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert 'keep_alive' in call_args[1]['json']
        assert call_args[1]['json']['keep_alive'] == '0s'
        assert call_args[1]['json']['model'] == 'llama2:latest'

    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_stop_model_not_running(self, mock_status, mock_running, client):
        """Test stopping a model that is not currently running."""
        mock_status.return_value = True
        mock_running.return_value = []

        response = client.post('/api/models/stop/llama2:latest')

        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'not currently running' in data['message'].lower()

    @patch('app.routes.main.ollama_service.get_service_status')
    def test_stop_model_service_not_running(self, mock_status, client):
        """Test stopping a model when Ollama service is down."""
        mock_status.return_value = False

        response = client.post('/api/models/stop/llama2:latest')

        assert response.status_code == 503
        data = response.get_json()
        assert data['success'] is False
        assert 'service is not running' in data['message'].lower()

    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_stop_model_timeout(self, mock_status, mock_running, mock_post, client):
        """Test stopping a model that times out."""
        mock_status.return_value = True
        mock_running.return_value = [{'name': 'llama2:latest', 'size': 1000000}]

        mock_post.side_effect = requests.exceptions.Timeout()

        response = client.post('/api/models/stop/llama2:latest')

        assert response.status_code == 504
        data = response.get_json()
        assert data['success'] is False
        assert 'timeout' in data['message'].lower()


class TestModelRestart:
    """Test suite for model restart endpoint."""

    @patch('time.sleep')
    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_restart_running_model_success(self, mock_status, mock_running, mock_post, mock_sleep, client):
        """Test successfully restarting a running model."""
        mock_status.return_value = True
        mock_running.return_value = [{'name': 'llama2:latest', 'size': 1000000}]

        stop_response = Mock()
        stop_response.status_code = 200

        start_response = Mock()
        start_response.status_code = 200
        start_response.json.return_value = {'response': 'test'}

        mock_post.side_effect = [stop_response, start_response]

        response = client.post('/api/models/restart/llama2:latest')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'restarted successfully' in data['message'].lower()
        assert mock_post.call_count == 2

    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_restart_stopped_model_success(self, mock_status, mock_running, mock_post, client):
        """Test restarting a model that is not currently running."""
        mock_status.return_value = True
        mock_running.return_value = []

        start_response = Mock()
        start_response.status_code = 200
        start_response.json.return_value = {'response': 'test'}
        mock_post.return_value = start_response

        response = client.post('/api/models/restart/llama2:latest')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert mock_post.call_count == 1

    @patch('time.sleep')
    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_restart_model_start_fails_with_retry(self, mock_status, mock_running, mock_post, mock_sleep, client):
        """Test restart with retry on transient error."""
        mock_status.return_value = True
        mock_running.return_value = []

        fail_response = Mock()
        fail_response.status_code = 503
        fail_response.json.return_value = {'error': 'Service temporarily unavailable'}

        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {'response': 'test'}

        mock_post.side_effect = [fail_response, success_response]

        response = client.post('/api/models/restart/llama2:latest')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    @patch('app.routes.main.ollama_service.get_service_status')
    def test_restart_model_service_not_running(self, mock_status, client):
        """Test restart when Ollama service is down."""
        mock_status.return_value = False

        response = client.post('/api/models/restart/llama2:latest')

        assert response.status_code == 503
        data = response.get_json()
        assert data['success'] is False
        assert 'service is not running' in data['message'].lower()


class TestModelDelete:
    """Test suite for model delete endpoint."""

    @patch('app.routes.main.requests.delete')
    @patch('app.routes.main.ollama_service.get_available_models')
    @patch('app.routes.main.ollama_service.get_running_models')
    def test_delete_model_success(self, mock_running, mock_available, mock_delete, client):
        """Test successfully deleting a model."""
        mock_running.return_value = []
        mock_available.return_value = [{'name': 'llama2:latest', 'size': 1000000}]

        delete_response = Mock()
        delete_response.status_code = 200
        mock_delete.return_value = delete_response

        response = client.delete('/api/models/delete/llama2:latest')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    @patch('app.routes.main.ollama_service.get_available_models')
    @patch('app.routes.main.ollama_service.get_running_models')
    def test_delete_nonexistent_model(self, mock_running, mock_available, client):
        """Test deleting a model that doesn't exist."""
        mock_running.return_value = []
        mock_available.return_value = []

        response = client.delete('/api/models/delete/nonexistent:latest')

        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False


class TestModelStart:
    """Test suite for model start endpoint."""

    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_start_model_success(self, mock_status, mock_running, mock_post, client):
        """Test successfully starting a model."""
        mock_status.return_value = True
        mock_running.return_value = []

        start_response = Mock()
        start_response.status_code = 200
        start_response.json.return_value = {'response': 'test'}
        mock_post.return_value = start_response

        response = client.post('/api/models/start/llama2:latest')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_start_already_running_model(self, mock_status, mock_running, client):
        """Test starting a model that is already running."""
        mock_status.return_value = True
        mock_running.return_value = [{'name': 'llama2:latest', 'size': 1000000}]

        response = client.post('/api/models/start/llama2:latest')

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'already running' in data['message'].lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
