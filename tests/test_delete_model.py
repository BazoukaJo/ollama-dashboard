#!/usr/bin/env python3
"""Test the delete_model endpoint without touching real models.

Uses mocks so no actual model is deleted. Tests the endpoint logic and response handling.
"""

import pytest
from unittest.mock import patch, MagicMock
from app import create_app


# Fake model name - never used for real deletion
TEST_MODEL_NAME = "test-delete-dummy-model:0.1b"


def test_delete_model_endpoint_mocked():
    """Test delete endpoint with mocked Ollama API - no real model is deleted."""
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # Mock the HTTP session delete to Ollama - returns success, no real API call
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.routes.main.ollama_service._session") as mock_session, \
         patch(
             "app.services.model_settings_helpers.delete_model_settings_entry",
             return_value=True,
         ):
        mock_session.delete.return_value = mock_response

        response = client.delete(f"/api/models/delete/{TEST_MODEL_NAME}")
        data = response.get_json()

        assert response.status_code == 200
        assert data.get("success") is True
        assert "deleted successfully" in data.get("message", "").lower()

        # Verify we would have called Ollama delete with correct params
        mock_session.delete.assert_called_once()
        call_args = mock_session.delete.call_args
        assert call_args[1]["json"]["name"] == TEST_MODEL_NAME


def test_delete_model_endpoint_error_handling():
    """Test delete endpoint when Ollama returns an error."""
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"error": "model not found"}
    mock_response.text = "model not found"

    with patch("app.routes.main.ollama_service._session") as mock_session:
        mock_session.delete.return_value = mock_response

        response = client.delete(f"/api/models/delete/{TEST_MODEL_NAME}")
        data = response.get_json()

        assert response.status_code == 400
        assert data.get("success") is False
        assert "error" in data.get("message", "").lower() or "not found" in data.get("message", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
