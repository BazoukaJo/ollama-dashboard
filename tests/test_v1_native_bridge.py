"""Tests for OpenAI v1 → native Ollama bridge."""
from app.services.v1_native_bridge import (
    apply_copilot_native_defaults,
    merge_v1_payload_options,
    native_chat_response_to_openai,
    openai_chat_to_native,
    prepare_v1_chat_completions_payload,
    stream_native_chat_lines_to_openai_sse,
)


def test_apply_copilot_native_defaults_preserves_agent_model_defaults():
    native = {
        'model': 'qwen3:14b',
        'messages': [],
        'tools': [{'type': 'function', 'function': {'name': 'read_file', 'parameters': {}}}],
    }
    apply_copilot_native_defaults(native, {'model': 'qwen3:14b', 'messages': [], 'reasoning_effort': 'medium'})
    assert 'think' not in native


def test_apply_copilot_native_defaults_disables_thinking():
    native = openai_chat_to_native(
        {'model': 'gemma4:latest', 'messages': [{'role': 'user', 'content': 'hi'}], 'stream': True},
        {},
    )
    apply_copilot_native_defaults(native, {'model': 'gemma4:latest', 'messages': []})
    assert native['think'] is False


def test_apply_copilot_native_defaults_ignores_copilot_reasoning_effort():
    native = openai_chat_to_native(
        {
            'model': 'gemma4:latest',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'reasoning_effort': 'medium',
        },
        {},
    )
    apply_copilot_native_defaults(native, {'reasoning_effort': 'medium'})
    assert native['think'] is False


def test_apply_copilot_native_defaults_respects_client_reasoning(monkeypatch):
    monkeypatch.setenv('OLLAMA_COPILOT_ALLOW_THINKING', 'true')
    native = openai_chat_to_native(
        {
            'model': 'gemma4:latest',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'reasoning_effort': 'high',
        },
        {},
    )
    apply_copilot_native_defaults(native, {'reasoning_effort': 'high'})
    assert native['think'] == 'high'


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


def test_native_chat_response_maps_length_finish_to_stop():
    """Copilot crashes on finish_reason length — bridge must emit stop."""
    native = {
        'model': 'm',
        'message': {'role': 'assistant', 'content': 'partial'},
        'done': True,
        'done_reason': 'length',
    }
    out = native_chat_response_to_openai(native, copilot_safe=True)
    assert out['choices'][0]['finish_reason'] == 'stop'


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


def test_stream_omits_reasoning_deltas_for_copilot():
    """Copilot BYOK ignores delta.reasoning — buffer thinking and flush on done."""
    lines = [
        b'{"message":{"role":"assistant","thinking":"I","content":""},"done":false}',
        b'{"message":{"role":"assistant","thinking":" need","content":""},"done":false}',
        b'{"message":{"role":"assistant","content":"Hello!"},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='gemma4:latest', omit_reasoning_deltas=True,
    ))
    assert '"reasoning"' not in out
    assert 'Hello!' in out
    assert '"content": "I"' not in out and '"content":"I"' not in out


def test_stream_defers_early_content_during_thinking():
    """Short content-only token after thinking lines must not surface as lone answer."""
    lines = [
        b'{"message":{"role":"assistant","thinking":"I","content":""},"done":false}',
        b'{"message":{"role":"assistant","thinking":" need","content":""},"done":false}',
        b'{"message":{"role":"assistant","content":"I"},"done":false}',
        b'{"message":{"role":"assistant","content":"Hello!"},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='gemma4:latest', omit_reasoning_deltas=True,
    ))
    assert '"reasoning"' not in out
    assert 'Hello!' in out
    assert '"content": "I"' not in out and '"content":"I"' not in out


def test_native_chat_response_copilot_safe_replaces_bleed():
    native = {
        'model': 'gemma4:latest',
        'message': {'role': 'assistant', 'content': 'I', 'thinking': 'I need to greet the user.'},
        'done': True,
    }
    out = native_chat_response_to_openai(native, copilot_safe=True)
    assert 'reasoning' not in out['choices'][0]['message']
    assert out['choices'][0]['message']['content'] == 'I need to greet the user.'


def test_stream_omits_bleed_content_during_thinking():
    """Mixed thinking+content lines must not surface a lone thinking token in content."""
    lines = [
        b'{"message":{"role":"assistant","thinking":"I","content":"I"},"done":false}',
        b'{"message":{"role":"assistant","thinking":" need to answer","content":""},"done":false}',
        b'{"message":{"role":"assistant","content":"Hello!"},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='gemma4:latest', omit_reasoning_deltas=True,
    ))
    assert '"reasoning"' not in out
    assert 'Hello!' in out
    assert '"content": "I"' not in out and '"content":"I"' not in out


def test_stream_done_flush_includes_role_for_copilot():
    import json
    lines = [
        b'{"message":{"role":"assistant","thinking":"Only","content":""},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='m', omit_reasoning_deltas=True,
    ))
    for part in out.split('data: '):
        chunk = part.strip().split('\n\n')[0]
        if not chunk or chunk == '[DONE]':
            continue
        delta = json.loads(chunk)['choices'][0]['delta']
        if delta.get('content') and delta['content'] != '':
            assert delta.get('role') == 'assistant'


def test_stream_agent_tool_calls_do_not_flush_thinking_to_content():
    """Agent turns with tool_calls must emit tools, not buffered thinking as content."""
    lines = [
        b'{"message":{"role":"assistant","thinking":"Hello","content":""},"done":false}',
        b'{"message":{"role":"assistant","thinking":" there","content":""},"done":false}',
        b'{"message":{"role":"assistant","tool_calls":[{"function":{"name":"x","arguments":{}}}],"content":""},"done":false}',
        b'{"message":{"role":"assistant","content":""},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='m', omit_reasoning_deltas=True, agent_mode=True,
    ))
    assert 'Hello there' not in out
    assert '"tool_calls"' in out
    assert '"reasoning"' not in out


def test_stream_truncates_huge_tool_call_arguments(monkeypatch):
    """Agent-mode tool_calls must fit the IDE char budget (Copilot rejects oversized SSE)."""
    monkeypatch.setenv('OLLAMA_PROXY_MAX_RESPONSE_CHARS', '2048')
    huge = 'x' * 50_000
    lines = [
        (
            b'{"message":{"role":"assistant","tool_calls":[{"id":"c1","function":'
            b'{"name":"grep","arguments":{"pattern":"' + huge.encode() + b'"}}}],"content":""},'
            b'"done":true}'
        ),
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='qwen3:14b', omit_reasoning_deltas=True, agent_mode=True,
    ))
    assert '"tool_calls"' in out
    assert len(out) < 50_000


def test_native_chat_response_maps_length_finish_to_stop_with_tools():
    native = {
        'model': 'm',
        'message': {
            'role': 'assistant',
            'content': '',
            'tool_calls': [{'function': {'name': 'x', 'arguments': {}}}],
        },
        'done': True,
        'done_reason': 'length',
    }
    out = native_chat_response_to_openai(native, copilot_safe=False)
    assert out['choices'][0]['finish_reason'] == 'stop'


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


def test_stream_emits_content_when_only_present_on_done_line():
    lines = [
        b'{"message":{"role":"assistant","content":""},"done":false}',
        b'{"message":{"role":"assistant","content":"A cat on a mat."},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(iter(lines), model='qwen3-vl:8b'))
    assert 'A cat on a mat.' in out
    assert 'data: [DONE]' in out


def test_stream_maps_thinking_to_reasoning_delta():
    lines = [
        b'{"message":{"role":"assistant","thinking":"Hmm","content":""},"done":false}',
        b'{"message":{"role":"assistant","thinking":"","content":"Hi"},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='qwen3:14b', mirror_thinking_to_content=False,
    ))
    assert '"reasoning": "Hmm"' in out or '"reasoning":"Hmm"' in out
    assert '"content": "Hmm"' not in out and '"content":"Hmm"' not in out
    assert '"role": "assistant"' in out or '"role":"assistant"' in out
    assert '"content": "Hi"' in out or '"content":"Hi"' in out
    assert 'data: [DONE]' in out


def test_stream_mirrors_thinking_to_content_for_copilot():
    """VS Code Copilot BYOK renders delta.content only — mirror thinking while streaming."""
    lines = [
        b'{"message":{"role":"assistant","thinking":"Hmm","content":""},"done":false}',
        b'{"message":{"role":"assistant","thinking":"","content":"Hi"},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='qwen3:14b', mirror_thinking_to_content=True,
    ))
    assert '"content": "Hmm"' in out or '"content":"Hmm"' in out
    assert '"content": "Hi"' in out or '"content":"Hi"' in out
    assert '"reasoning"' not in out
    assert 'reasoning_content' not in out
    assert 'data: [DONE]' in out


def test_stream_keeps_role_on_content_deltas_for_copilot():
    """Copilot BYOK expects Ollama-shaped chunks: role + content on every delta."""
    import json
    lines = [
        b'{"message":{"role":"assistant","content":"Hello"},"done":false}',
        b'{"message":{"role":"assistant","content":"!"},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='m', mirror_thinking_to_content=True,
    ))
    content_deltas = []
    for part in out.split('data: '):
        chunk = part.strip().split('\n\n')[0]
        if not chunk or chunk == '[DONE]':
            continue
        delta = json.loads(chunk)['choices'][0]['delta']
        if delta.get('content'):
            content_deltas.append(delta)
    assert content_deltas
    assert all(d.get('role') == 'assistant' for d in content_deltas)


def test_stream_thinking_visible_when_reasoning_fills_budget():
    """Reasoning-only chunks must not consume the content char budget."""
    import json
    budget = 5000
    chunk = 'x' * 1000
    lines = [
        json.dumps({
            'message': {'role': 'assistant', 'thinking': chunk, 'content': ''},
            'done': False,
        }).encode()
        for _ in range(10)
    ]
    lines.append(json.dumps({
        'message': {'role': 'assistant', 'thinking': '', 'content': ''},
        'done': True,
    }).encode())
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines),
        model='test',
        max_stream_chars=budget,
        mirror_thinking_to_content=True,
    ))
    assert 'x' * 100 in out
    assert 'data: [DONE]' in out


def test_stream_flushes_thinking_to_content_when_no_answer():
    """Copilot BYOK only renders delta.content — flush thinking on done when needed."""
    lines = [
        b'{"message":{"role":"assistant","thinking":"Only","content":""},"done":false}',
        b'{"message":{"role":"assistant","thinking":" thinking","content":""},"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(iter(lines), model='qwen3-vl:8b'))
    assert 'Only thinking' in out
    assert 'data: [DONE]' in out
