"""Tests for Copilot numeric model index resolution."""
from unittest.mock import patch

from app.services.v1_model_resolve import invalidate_model_list_cache, resolve_v1_model_name


def setup_function():
    invalidate_model_list_cache()


def test_resolve_passthrough_string_model():
    assert resolve_v1_model_name('http://localhost:11434', 'qwen3:14b') == 'qwen3:14b'


def test_resolve_numeric_index():
    fake_ids = ['gemma4:latest', 'gpt-oss:20b', 'qwen3:14b']

    with patch('app.services.v1_model_resolve._fetch_v1_model_ids', return_value=fake_ids):
        assert resolve_v1_model_name('http://localhost:11434', '2') == 'qwen3:14b'
        assert resolve_v1_model_name('http://localhost:11434', 2) == 'qwen3:14b'


def test_resolve_out_of_range_index_unchanged():
    with patch('app.services.v1_model_resolve._fetch_v1_model_ids', return_value=['a']):
        assert resolve_v1_model_name('http://localhost:11434', '99') == '99'
