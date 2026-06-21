"""Tests for context length display formatting."""

from app.services.model_helpers import (
    format_context_length,
    normalize_context_display_fields,
)


def test_format_context_length_raw_int():
    assert format_context_length(262144) == "262K"
    assert format_context_length(16384) == "16K"
    assert format_context_length(128000) == "128K"
    assert format_context_length(1_500_000) == "1M"


def test_format_context_length_numeric_string():
    assert format_context_length("262144") == "262K"
    assert format_context_length("16,384") == "16K"


def test_format_context_length_already_formatted():
    assert format_context_length("262K") == "262K"
    assert format_context_length("262k") == "262K"
    assert format_context_length("128K") == "128K"


def test_normalize_context_display_fields():
    model = {
        "context_length": 262144,
        "loaded_context_length": 16384,
        "request_context_length": "8192",
        "details": {"context_length": 262144},
    }
    normalize_context_display_fields(model)
    assert model["context_length"] == "262K"
    assert model["loaded_context_length"] == "16K"
    assert model["request_context_length"] == "8K"
    assert model["details"]["context_length"] == "262K"
