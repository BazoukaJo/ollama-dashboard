"""Tests for Ask? chat message preparation."""
from app.services.chat_prep import (
    model_has_tools,
    model_has_vision,
    normalize_ask_messages,
)


def test_normalize_ask_messages_filters_roles():
    out = normalize_ask_messages([
        {'role': 'user', 'content': 'hi'},
        {'role': 'tool', 'content': 'ignored'},
        {'role': 'assistant', 'content': 'hello'},
    ])
    assert len(out) == 2
    assert out[0]['role'] == 'user'
    assert out[1]['role'] == 'assistant'


def test_normalize_ask_messages_empty_for_non_list():
    assert normalize_ask_messages(None) == []
    assert normalize_ask_messages('bad') == []


def test_model_has_vision_from_capabilities():
    assert model_has_vision({'capabilities': ['vision']}) is True
    assert model_has_vision({'capabilities': ['text']}) is False


def test_model_has_tools_explicit_false():
    assert model_has_tools({'has_tools': False}) is False
    assert model_has_tools({'has_tools': True}) is True
