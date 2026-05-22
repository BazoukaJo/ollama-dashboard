from unittest.mock import MagicMock, patch

import pytest
import requests
from app import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with app.test_client() as c:
        yield c

@patch('app.routes.main.ollama_service._session.post')
@patch('app.routes.main.ollama_service.get_running_models')
@patch('app.routes.main.ollama_service.get_service_status')
def test_start_model_success(mock_status, mock_running, mock_session_post, client):
    mock_status.return_value = True
    mock_running.return_value = []
    success_resp = MagicMock(status_code=200, text='ok')
    success_resp.json.return_value = {}
    mock_session_post.return_value = success_resp
    resp = client.post('/api/models/start/test-model')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success']
    assert 'started successfully' in data['message']

@patch('app.routes.main.ollama_service._session.post')
@patch('app.routes.main.ollama_service.get_running_models')
@patch('app.routes.main.ollama_service.get_service_status')
def test_start_model_service_down(mock_status, mock_running, _, client):
    mock_status.return_value = False
    mock_running.return_value = []
    resp = client.post('/api/models/start/test-model')
    assert resp.status_code == 503
    data = resp.get_json()
    assert not data['success']
    assert 'service is not running' in data['message']

@patch('app.routes.main.ollama_service._session.post')
@patch('app.routes.main.ollama_service.get_running_models')
@patch('app.routes.main.ollama_service.get_service_status')
def test_start_model_already_running(mock_status, mock_running, _, client):
    mock_status.return_value = True
    mock_running.return_value = [{'name': 'test-model'}]
    resp = client.post('/api/models/start/test-model')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success']
    assert 'already running' in data['message']


@patch('app.routes.main.ollama_service._session.post')
@patch('app.routes.main.ollama_service.get_running_models')
@patch('app.routes.main.ollama_service.get_service_status')
def test_start_model_retry_timeout_is_capped(mock_status, mock_running, mock_post, client):
    """Generate retry timeout must never exceed the configured hard cap."""
    mock_status.return_value = True
    mock_running.return_value = []
    mock_post.side_effect = requests.exceptions.Timeout()

    resp = client.post('/api/models/start/test-model')
    assert resp.status_code == 408

    timeouts = [kwargs.get('timeout') for _args, kwargs in mock_post.call_args_list]
    assert timeouts, 'Expected at least one generate call'
    assert max(int(t) for t in timeouts if t is not None) <= 120
