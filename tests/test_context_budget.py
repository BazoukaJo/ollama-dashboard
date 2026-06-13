"""Tests for context budget trimming."""
from app.services.context_budget import (
    completion_budget,
    estimate_messages_tokens,
    estimate_tokens,
    trim_messages_to_budget,
)


def test_estimate_tokens():
    assert estimate_tokens('') == 0
    assert estimate_tokens('abcd') == 1
    assert estimate_tokens('a' * 40) == 10


def test_trim_removes_oldest_messages():
    messages = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'x' * 20000},
        {'role': 'assistant', 'content': 'y' * 20000},
        {'role': 'user', 'content': 'recent'},
    ]
    trimmed, meta = trim_messages_to_budget(messages, num_ctx=4096)
    assert meta['trimmed'] is True
    assert meta['messages_removed'] >= 1
    assert trimmed[0]['role'] == 'system'
    assert trimmed[-1]['content'] == 'recent'
    assert estimate_messages_tokens(trimmed) <= completion_budget(4096)


def test_no_trim_when_under_budget():
    messages = [{'role': 'user', 'content': 'hi'}]
    trimmed, meta = trim_messages_to_budget(messages, num_ctx=8192)
    assert meta['trimmed'] is False
    assert len(trimmed) == 1
