import pytest
from app import create_app


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture()
def client(monkeypatch):
    """Flask test client with mocked Ollama /api/ps and /api/tags."""
    app = create_app()
    client = app.test_client()

    # Sample available models (/api/tags)
    tags_payload = {
        "models": [
            {
                "name": "test-model",
                "size": 1024 * 1024 * 1024,
                "details": {
                    "family": "test-family",
                    "parameter_size": "7B",
                    "context_length": 8192,
                },
            }
        ]
    }

    # Sample running models (/api/ps)
    ps_payload = {
        "models": [
            {
                "name": "test-model",
                "size": 1024 * 1024 * 1024,
                "details": {
                    # Intentionally omit parameter_size here so it must be
                    # filled from the /api/tags metadata.
                    "family": "test-family",
                },
            }
        ]
    }

    def fake_get(self, url, timeout=10, **_kwargs):
        if url.endswith("/api/tags"):
            return DummyResponse(tags_payload, status_code=200)
        if url.endswith("/api/ps"):
            return DummyResponse(ps_payload, status_code=200)
        # Default: empty response
        return DummyResponse({"models": []}, status_code=200)

    monkeypatch.setattr("requests.Session.get", fake_get)
    return client


def test_running_models_have_parameter_size_from_available(client):
    """Running models should expose details.parameter_size when available from tags."""
    resp = client.get("/api/models/running")
    assert resp.status_code == 200
    data = resp.get_json()
    models = data.get("models", [])
    assert models, "Expected at least one running model"

    model = next((m for m in models if m.get("name") == "test-model"), None)
    assert model is not None, "test-model should be in running models"

    details = model.get("details") or {}
    param_size = details.get("parameter_size")
    assert (
        param_size == "7B"
    ), f"Expected parameter_size '7B' on running model, got {param_size!r}"

