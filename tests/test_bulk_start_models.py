"""Tests for the /api/models/bulk/start endpoint.

All tests are fully mocked — no live Ollama server required.
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
# Success paths
# ---------------------------------------------------------------------------

@patch('app.routes.main.ollama_service.clear_cache')
@patch('app.routes.main.ollama_service._session')
def test_bulk_start_all_succeed(mock_session, mock_clear, client):
    """All models start successfully — results list has success=True for each."""
    ok_resp = MagicMock(status_code=200, text='ok')
    mock_session.post.return_value = ok_resp

    resp = client.post(
        '/api/models/bulk/start',
        json={'models': ['llama2:latest', 'phi3:mini']},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'results' in data
    assert len(data['results']) == 2
    assert all(r['success'] for r in data['results'])


@patch('app.routes.main.ollama_service.clear_cache')
@patch('app.routes.main.ollama_service._session')
def test_bulk_start_cache_is_cleared(mock_session, mock_clear, client):
    """Cache is always cleared after a bulk start, even on partial failure."""
    mock_session.post.return_value = MagicMock(status_code=200, text='ok')

    client.post('/api/models/bulk/start', json={'models': ['llama2:latest']})
    mock_clear.assert_called_with('running_models')


@patch('app.routes.main.ollama_service.clear_cache')
@patch('app.routes.main.ollama_service._session')
def test_bulk_start_partial_failure(mock_session, mock_clear, client):
    """One model fails — that entry has success=False, others still succeed."""
    def side_effect(*args, **kwargs):
        payload = kwargs.get('json', {})
        if payload.get('model') == 'bad-model:latest':
            return MagicMock(status_code=404, text='not found')
        return MagicMock(status_code=200, text='ok')

    mock_session.post.side_effect = side_effect

    resp = client.post(
        '/api/models/bulk/start',
        json={'models': ['llama2:latest', 'bad-model:latest']},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    results_by_model = {r['model']: r for r in data['results']}
    assert results_by_model['llama2:latest']['success'] is True
    assert results_by_model['bad-model:latest']['success'] is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@patch('app.routes.main.ollama_service.clear_cache')
@patch('app.routes.main.ollama_service._session')
def test_bulk_start_empty_list(mock_session, mock_clear, client):
    """Empty model list returns empty results without calling Ollama."""
    resp = client.post('/api/models/bulk/start', json={'models': []})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['results'] == []
    mock_session.post.assert_not_called()


@patch('app.routes.main.ollama_service.clear_cache')
def test_bulk_start_missing_body(mock_clear, client):
    """Request with no body defaults to empty model list, returns empty results."""
    # No body, no content-type — get_json() returns None, falls back to {}
    resp = client.post('/api/models/bulk/start')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['results'] == []


@patch('app.routes.main.ollama_service.clear_cache')
def test_bulk_start_invalid_model_names_rejected(mock_clear, client):
    """Model names that fail validation appear in results with success=False."""
    resp = client.post(
        '/api/models/bulk/start',
        json={'models': ['../../etc/passwd', 'valid-model:latest']},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    results_by_model = {r['model']: r for r in data['results']}
    assert results_by_model['../../etc/passwd']['success'] is False


@patch('app.routes.main.ollama_service.clear_cache')
@patch('app.routes.main.ollama_service._session')
def test_bulk_start_keep_alive_passed(mock_session, mock_clear, client):
    """keep_alive='24h' is included in the Ollama generate payload."""
    mock_session.post.return_value = MagicMock(status_code=200, text='ok')

    client.post('/api/models/bulk/start', json={'models': ['llama2:latest']})

    call_kwargs = mock_session.post.call_args
    payload = call_kwargs[1].get('json') or call_kwargs[0][1]
    assert payload.get('keep_alive') == '24h'
