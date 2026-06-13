"""Tests for OpenAI v1 → native Ollama bridge."""
from app.services.v1_native_bridge import (
    merge_v1_payload_options,
    native_chat_response_to_openai,
    openai_chat_to_native,
    prepare_v1_chat_completions_payload,
    stream_native_chat_lines_to_openai_sse,
)


def test_openai_chat_to_native_merges_dashboard_num_ctx():
    payload = {
        'model': 'qwen3:14b',
        'messages': [{'role': 'user', 'content': 'hi'}],
        'temperature': 0.9,
        'max_tokens': 512,
    }
    dashboard = {'temperature': 0.6, 'num_ctx': 40000}
    native = openai_chat_to_native(payload, dashboard)
    assert native['model'] == 'qwen3:14b'
    assert native['options']['num_ctx'] == 40000
    assert native['options']['temperature'] == 0.6
    assert native['options']['num_predict'] == 512


def test_merge_v1_payload_options_preserves_client_only_keys():
    payload = {'temperature': 0.8, 'options': {'extra_client_opt': 'x'}}
    merged = merge_v1_payload_options(payload, {'num_ctx': 8192})
    assert merged['extra_client_opt'] == 'x'
    assert merged['num_ctx'] == 8192


def test_native_chat_response_to_openai_shape():
    native = {
        'model': 'm',
        'message': {'role': 'assistant', 'content': 'hello'},
        'done': True,
        'prompt_eval_count': 10,
        'eval_count': 5,
    }
    out = native_chat_response_to_openai(native, completion_id='chatcmpl-test')
    assert out['object'] == 'chat.completion'
    assert out['id'] == 'chatcmpl-test'
    assert out['choices'][0]['message']['content'] == 'hello'
    usage = out['usage']
    assert isinstance(usage, dict)
    assert usage.get('total_tokens') == 15


def test_native_chat_response_includes_reasoning():
    native = {
        'model': 'qwen3:14b',
        'message': {'role': 'assistant', 'content': 'Hi', 'thinking': 'Let me greet.'},
        'done': True,
    }
    out = native_chat_response_to_openai(native)
    assert out['choices'][0]['message']['content'] == 'Hi'
    assert out['choices'][0]['message']['reasoning'] == 'Let me greet.'


def test_prepare_v1_chat_completions_payload_merges_options():
    payload = {
        'model': 'qwen3:14b',
        'messages': [{'role': 'user', 'content': 'hi'}],
        'temperature': 0.9,
    }
    out = prepare_v1_chat_completions_payload(payload, {'num_ctx': 32000, 'temperature': 0.6})
    assert out['messages'] == payload['messages']
    assert out['options']['num_ctx'] == 32000
    assert out['options']['temperature'] == 0.6


def test_stream_maps_tool_calls_to_openai_format():
    lines = [
        b'{"message":{"role":"assistant","tool_calls":[{"id":"call_x","function":{"index":0,"name":"calc","arguments":{"expr":"2+2"}}}]},"done":false}',
        b'{"message":{"role":"assistant","content":""},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(iter(lines), model='qwen3:14b'))
    assert '"arguments": "{\\"expr\\": \\"2+2\\"}"' in out or '"arguments":"{\\"expr\\": \\"2+2\\"}"' in out
    assert '"finish_reason": "tool_calls"' in out or '"finish_reason":"tool_calls"' in out
    assert '"role": "assistant"' in out
    assert '"tool_calls"' in out


def test_stream_maps_thinking_to_reasoning_delta():
    lines = [
        b'{"message":{"role":"assistant","thinking":"Hmm","content":""},"done":false}',
        b'{"message":{"role":"assistant","thinking":"","content":"Hi"},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(iter(lines), model='qwen3:14b'))
    assert '"reasoning": "Hmm"' in out or '"reasoning":"Hmm"' in out
    assert '"role": "assistant"' in out or '"role":"assistant"' in out
    assert '"content": "Hi"' in out or '"content":"Hi"' in out
    assert 'data: [DONE]' in out
