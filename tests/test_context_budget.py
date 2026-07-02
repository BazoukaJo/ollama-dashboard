"""Tests for context budget estimation."""
from app.services.context_budget import (
    _truncate_string_to_tokens,
    estimate_messages_tokens,
    trim_messages_to_budget,
)


def test_image_messages_cost_more_tokens_than_text_only():
    text_only = [{'role': 'user', 'content': 'hello'}]
    with_image = [{
        'role': 'user',
        'content': 'hello',
        'images': ['abc', 'def'],
    }]
    assert estimate_messages_tokens(with_image) > estimate_messages_tokens(text_only)


def test_tool_calls_counted_when_assistant_content_empty():
    msgs = [{
        'role': 'assistant',
        'content': '',
        'tool_calls': [{
            'id': '1',
            'type': 'function',
            'function': {'name': 'read', 'arguments': '{"x": "' + ('y' * 4000) + '"}'},
        }],
    }]
    assert estimate_messages_tokens(msgs) > 500


def test_trim_considers_image_heuristic():
    msgs = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'old', 'images': ['a'] * 8},
        {'role': 'user', 'content': 'keep me'},
    ]
    trimmed, meta = trim_messages_to_budget(msgs, 512)
    assert meta['trimmed'] is True
    assert trimmed[-1]['content'] == 'keep me'


def test_trim_truncates_single_huge_message_instead_of_dropping():
    huge = 'file content line\n' * 16000
    msgs = [
        {'role': 'system', 'content': 'You are Copilot.'},
        {'role': 'user', 'content': huge},
    ]
    trimmed, meta = trim_messages_to_budget(msgs, 16384)
    assert meta['trimmed'] is True
    assert len(trimmed) == 2
    assert trimmed[-1]['role'] == 'user'
    assert trimmed[-1]['content']
    assert len(trimmed[-1]['content']) < len(huge)
    assert 'trimmed by ollama-dashboard proxy' in trimmed[-1]['content']
    assert estimate_messages_tokens(trimmed) <= meta['budget']


def test_trim_preserves_last_user_question_in_history():
    msgs = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'x' * 30000},
        {'role': 'assistant', 'content': 'y' * 30000},
        {'role': 'user', 'content': 'final question'},
    ]
    trimmed, meta = trim_messages_to_budget(msgs, 4096)
    assert trimmed[-1]['content'] == 'final question'
    assert meta['trimmed'] is True


def test_trim_truncates_oversized_system_prompt():
    msgs = [
        {'role': 'system', 'content': 'x' * 50000},
        {'role': 'user', 'content': 'real question'},
    ]
    trimmed, meta = trim_messages_to_budget(msgs, 4096)
    assert trimmed[-1]['content'] == 'real question'
    assert len(trimmed[0]['content']) < 50000
    assert meta['content_truncated'] >= 1
    assert estimate_messages_tokens(trimmed) <= meta['budget']


def test_trim_huge_system_does_not_crush_user_to_few_tokens():
    """Copilot-sized system prompts must not leave only a handful of user tokens."""
    msgs = [
        {'role': 'system', 'content': 'x' * 200_000},
        {'role': 'user', 'content': 'What is 2+2?'},
    ]
    trimmed, meta = trim_messages_to_budget(msgs, 16384)
    assert trimmed[-1]['content'] == 'What is 2+2?'
    assert estimate_messages_tokens(trimmed) >= 128
    assert meta['trimmed'] is True


def test_trim_tool_calls_message_survives_budget():
    big_args = '{"body": "' + ('z' * 20000) + '"}'
    msgs = [
        {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': '1', 'type': 'function', 'function': {'name': 'read', 'arguments': big_args}},
            {'id': '2', 'type': 'function', 'function': {'name': 'read', 'arguments': '{}'}},
        ]},
        {'role': 'user', 'content': 'continue'},
    ]
    trimmed, meta = trim_messages_to_budget(msgs, 2048)
    assert trimmed[-1]['content'] == 'continue'
    assert meta['messages_removed'] >= 1 or meta['content_truncated'] >= 1
    assert meta['trimmed'] is True


def test_truncate_snaps_to_word_boundary_not_mid_word():
    """Truncation must not split a word/identifier in half at the head or tail cut point."""
    from app.services.context_budget import _TRUNCATION_MARKER

    head_word = 'supercalifragilisticexpialidocious'
    tail_word = 'antidisestablishmentarianism'
    text = f'{head_word} ' + ('middle filler content ' * 200) + f' {tail_word}'
    result = _truncate_string_to_tokens(text, max_tokens=100)
    assert _TRUNCATION_MARKER in result
    head_kept, tail_kept = result.split(_TRUNCATION_MARKER, 1)
    # The kept head must end at a word boundary (empty, or right after a space/newline).
    assert head_kept == '' or head_kept[-1] in (' ', '\n')
    # The kept tail must start at a word boundary (empty, or right after a space/newline
    # relative to the source text — i.e. it isn't a partial-word fragment).
    if tail_kept:
        assert text[text.index(tail_kept) - 1] in (' ', '\n')


def test_truncate_falls_back_to_hard_cut_when_no_whitespace_nearby():
    """A long unbroken string (no spaces) still truncates safely without erroring."""
    text = 'x' * 5000
    result = _truncate_string_to_tokens(text, max_tokens=100)
    assert 'trimmed by ollama-dashboard proxy' in result
    assert len(result) <= 100 * 4
