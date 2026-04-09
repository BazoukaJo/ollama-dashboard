"""Tests for InputValidator model name rules."""
import pytest
from app.services.validators import InputValidator


@pytest.mark.parametrize(
    "name",
    [
        "llama3.1:8b",
        "VladimirGav/gemma4-26b-16GB-VRAM:latest",
        "repo/model+quant:latest",
        "hf.co/org/model:q4",
    ],
)
def test_validate_model_name_allows_library_and_plus(name):
    ok, msg = InputValidator.validate_model_name(name)
    assert ok is True
    assert msg == ""


def test_validate_model_name_rejects_injection_like():
    ok, msg = InputValidator.validate_model_name("x;rm -rf /")
    assert ok is False
    assert "Invalid model name" in msg


def test_non_api_404_returns_html_not_raw_exception():
    from app import create_app

    app = create_app()
    with app.test_client() as client:
        resp = client.get("/this-route-does-not-exist-ollama-dash")
    assert resp.status_code == 404
    assert "text/html" in (resp.content_type or "")
    assert b"Not Found" in resp.data
