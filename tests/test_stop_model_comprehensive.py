"""Comprehensive tests for the stop_model endpoint.

All tests are fully mocked — no live Ollama server is required.
"""
import pytest
from unittest.mock import patch, MagicMock
from app import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

@patch('app.routes.main.requests.post')
@patch('app.routes.main._verify_model_unloaded')
@patch('app.routes.main.ollama_service.get_running_models')
@patch('app.routes.main.ollama_service.get_service_status')
def test_stop_model_success(mock_status, mock_running, mock_verify, mock_post, client):
    """Stopping a running model returns 200 with success=True."""
    mock_status.return_value = True
    mock_running.return_value = [{'name': 'llama2:latest'}]
    mock_post.return_value = MagicMock(status_code=200, text='ok')
    mock_verify.return_value = True

    resp = client.post('/api/models/stop/llama2:latest')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'stopped' in data['message'].lower()


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------

@patch('app.routes.main.ollama_service.get_service_status')
def test_stop_model_service_not_running(mock_status, client):
    """Returns 503 when Ollama service is stopped."""
    mock_status.return_value = False
    resp = client.post('/api/models/stop/llama2:latest')
    assert resp.status_code == 503
    data = resp.get_json()
    assert data['success'] is False


@patch('app.routes.main.ollama_service.get_running_models')
@patch('app.routes.main.ollama_service.get_service_status')
def test_stop_model_not_running(mock_status, mock_running, client):
    """Returns 400 when the model is not currently running."""
    mock_status.return_value = True
    mock_running.return_value = []  # model is not loaded

    resp = client.post('/api/models/stop/llama2:latest')
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


# ---------------------------------------------------------------------------
# Ollama API error handling
# ---------------------------------------------------------------------------

@patch('app.routes.main.requests.post')
@patch('app.routes.main.ollama_service.get_running_models')
@patch('app.routes.main.ollama_service.get_service_status')
def test_stop_model_ollama_404(mock_status, mock_running, mock_post, client):
    """Returns 404 when Ollama says the model does not exist."""
    mock_status.return_value = True
    mock_running.return_value = [{'name': 'ghost-model:latest'}]
    mock_post.return_value = MagicMock(status_code=404, text='not found')

    resp = client.post('/api/models/stop/ghost-model:latest')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False


@patch('app.routes.main.requests.post')
@patch('app.routes.main.ollama_service.get_running_models')
@patch('app.routes.main.ollama_service.get_service_status')
def test_stop_model_ollama_500(mock_status, mock_running, mock_post, client):
    """Returns the Ollama error status when the unload call fails."""
    mock_status.return_value = True
    mock_running.return_value = [{'name': 'llama2:latest'}]
    mock_post.return_value = MagicMock(
        status_code=500,
        text='internal server error',
        json=MagicMock(return_value={'error': 'internal server error'}),
    )

    resp = client.post('/api/models/stop/llama2:latest')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['success'] is False


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_stop_model_invalid_name(client):
    """Returns 400 for a model name that exceeds the 255-char limit."""
    # Use 256 'a' chars — passes URL routing but fails InputValidator's length check
    long_name = 'a' * 256
    resp = client.post(f'/api/models/stop/{long_name}')
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False


# ---------------------------------------------------------------------------
# Backward-compat stub for external references
# ---------------------------------------------------------------------------

def test_stop_model_comprehensive():
    """Backward-compat entry point — kept as a no-op stub.
    The real coverage lives in the parameterised test functions above."""
