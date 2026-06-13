"""Tests for system prompt injection."""
from app.services.system_prompts import PRESETS, inject_system_prompt, resolve_system_prompt


def test_resolve_custom_over_preset():
    text = resolve_system_prompt({
        'system_prompt_preset': 'coding_assistant',
        'system_prompt_custom': 'Custom prompt',
    })
    assert text == 'Custom prompt'


def test_inject_prepends_system():
    msgs = inject_system_prompt([{'role': 'user', 'content': 'hi'}], PRESETS['coding_assistant'])
    assert msgs[0]['role'] == 'system'
    assert 'coding assistant' in msgs[0]['content'].lower()
    assert msgs[1]['content'] == 'hi'


def test_inject_merges_existing_system():
    msgs = inject_system_prompt(
        [{'role': 'system', 'content': 'Existing'}, {'role': 'user', 'content': 'q'}],
        'Preset line',
    )
    assert msgs[0]['role'] == 'system'
    assert 'Preset line' in msgs[0]['content']
    assert 'Existing' in msgs[0]['content']
