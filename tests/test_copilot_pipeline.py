"""Tests for Copilot payload pipeline."""
from app.services.copilot_pipeline import prepare_copilot_payload


def test_pipeline_merges_settings_and_trims():
    payload = {
        'model': 'qwen-test',
        'messages': [
            {'role': 'user', 'content': 'x' * 30000},
            {'role': 'assistant', 'content': 'y' * 30000},
            {'role': 'user', 'content': 'last'},
        ],
        'stream': True,
    }
    entry = {
        'settings': {'num_ctx': 4096, 'temperature': 0.2},
        'client': {
            'system_prompt_preset': 'coding_assistant',
            'context_trim_enabled': True,
        },
    }
    merged, meta = prepare_copilot_payload(payload, entry)
    assert merged['options']['num_ctx'] == 4096
    assert merged['options']['temperature'] == 0.2
    assert meta.get('system_prompt_injected') is True
    assert merged['messages'][0]['role'] == 'system'
    assert merged['messages'][-1]['content'] == 'last'


def test_pipeline_respects_trim_disabled():
    payload = {
        'model': 'm',
        'messages': [{'role': 'user', 'content': 'x' * 50000}],
    }
    entry = {
        'settings': {'num_ctx': 2048},
        'client': {'context_trim_enabled': False},
    }
    merged, meta = prepare_copilot_payload(payload, entry)
    assert 'context_trim' not in meta or not meta.get('context_trim', {}).get('trimmed')
