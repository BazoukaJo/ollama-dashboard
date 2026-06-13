"""Tests for context budget estimation."""
from app.services.context_budget import estimate_messages_tokens, trim_messages_to_budget


def test_image_messages_cost_more_tokens_than_text_only():
    text_only = [{'role': 'user', 'content': 'hello'}]
    with_image = [{
        'role': 'user',
        'content': 'hello',
        'images': ['abc', 'def'],
    }]
    assert estimate_messages_tokens(with_image) > estimate_messages_tokens(text_only)


def test_trim_considers_image_heuristic():
    msgs = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'old', 'images': ['a'] * 8},
        {'role': 'user', 'content': 'keep me'},
    ]
    trimmed, meta = trim_messages_to_budget(msgs, 512)
    assert meta['trimmed'] is True
    assert trimmed[-1]['content'] == 'keep me'
