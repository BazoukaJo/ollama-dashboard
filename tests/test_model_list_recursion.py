"""Regression tests for model-list recursion guards."""
from unittest.mock import patch

import pytest

from app.services.ollama import OllamaService


@pytest.fixture
def ollama_service():
    svc = OllamaService()
    yield svc


def test_get_available_models_does_not_recurse(ollama_service, monkeypatch):
    tags_payload = {
        'models': [
            {'name': 'gemma4:latest', 'size': 1, 'details': {'family': 'gemma4'}},
        ],
    }

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return tags_payload

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        ollama_service._session,
        'get',
        lambda *args, **kwargs: FakeResponse(),
    )
    monkeypatch.setattr(ollama_service, '_enrich_model_from_show', lambda m: (m.get('name'), None, None))
    monkeypatch.setattr(ollama_service, 'get_all_downloadable_models', lambda: [])

    models = ollama_service.get_available_models(force_refresh=True)
    assert len(models) == 1
    assert models[0]['name'] == 'gemma4:latest'


def test_get_available_models_survives_show_enrichment_timeout(ollama_service, monkeypatch):
    """Slow /api/show enrichment must not crash the model list endpoint."""
    import concurrent.futures

    tags_payload = {
        'models': [
            {'name': 'slow-model:latest', 'size': 1, 'details': {}},
        ],
    }

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return tags_payload

        def raise_for_status(self):
            return None

    monkeypatch.setattr(ollama_service._session, 'get', lambda *a, **k: FakeResponse())
    monkeypatch.setattr(
        ollama_service,
        '_enrich_model_from_show',
        lambda m: (m.get('name'), 8192, []),
    )
    monkeypatch.setattr(ollama_service, 'get_all_downloadable_models', lambda: [])
    ollama_service._building_available_models_depth = 0
    ollama_service.clear_cache('available_models')

    def timeout_as_completed(_futures, timeout=None):
        raise concurrent.futures.TimeoutError()

    monkeypatch.setattr(
        'app.services.ollama_models.concurrent.futures.as_completed',
        timeout_as_completed,
    )

    models = ollama_service.get_available_models(force_refresh=True)
    assert len(models) == 1
    assert models[0]['name'] == 'slow-model:latest'


def test_request_context_uses_stored_settings_only(ollama_service):
    from app.services.model_helpers import request_context_length_from_settings

    with patch('app.services.model_helpers.get_existing_model_settings_entry') as mock_existing, \
         patch.object(ollama_service, 'get_model_settings_with_fallback') as mock_fallback:
        mock_existing.return_value = {'settings': {'num_ctx': 16384}}
        result = request_context_length_from_settings(ollama_service, 'gemma4:latest')
    assert result == '16K'
    mock_fallback.assert_not_called()


def test_request_context_missing_when_not_stored(ollama_service):
    from app.services.model_helpers import request_context_length_from_settings

    with patch('app.services.model_helpers.get_existing_model_settings_entry', return_value=None), \
         patch.object(ollama_service, 'get_model_settings_with_fallback') as mock_fallback:
        result = request_context_length_from_settings(ollama_service, 'gemma4:latest')
    assert result is None
    mock_fallback.assert_not_called()
