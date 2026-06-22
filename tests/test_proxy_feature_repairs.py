"""Regression tests for the VS Code proxy + capability repairs.

Covers the high-impact fixes that make tools / reasoning / vision / MoE / streaming work
reliably through the dashboard proxy:
  * tool_calls truncation never emits invalid JSON (agent mode),
  * realistic tool_calls pass through whole,
  * agent-aware num_predict ceiling,
  * reasoning toggle resolves from the original (pre-sanitize) payload,
  * capability detection: API does not force reasoning False, family defaults, MoE,
  * provider capabilities[] from /api/tags are preserved,
  * unreachable Ollama yields an OpenAI-shaped error instead of an HTML 500.
"""
import json

import pytest
import requests
from app.services.capabilities import detect_capabilities, ensure_capability_flags
from app.services.client_payload_compat import (
    cap_num_predict,
    cap_openai_chat_response,
    proxy_max_response_chars,
    truncate_tool_calls,
)
from app.services.copilot_pipeline import prepare_copilot_payload
from app.services.model_helpers import normalize_available_model_entry
from app.services.v1_native_bridge import (
    apply_copilot_native_defaults,
    openai_chat_to_native,
    stream_native_chat_lines_to_openai_sse,
)


# --------------------------------------------------------------------------- #
# Tool-call JSON safety (the critical agent-mode fix)
# --------------------------------------------------------------------------- #
def _iter_stream_tool_call_arguments(sse_text):
    """Yield every function.arguments string found in an OpenAI SSE stream."""
    for part in sse_text.split('data: '):
        chunk = part.strip().split('\n\n')[0]
        if not chunk or chunk == '[DONE]':
            continue
        try:
            obj = json.loads(chunk)
        except ValueError:
            continue
        for choice in obj.get('choices', []):
            for tc in (choice.get('delta') or {}).get('tool_calls') or []:
                args = (tc.get('function') or {}).get('arguments')
                if isinstance(args, str) and args:
                    yield args


def test_truncate_oversized_tool_call_keeps_valid_json():
    huge = json.dumps({'content': 'x' * 500_000})
    calls = [{'id': 'c1', 'type': 'function', 'function': {'name': 'write', 'arguments': huge}}]
    out = truncate_tool_calls(calls, 16_384)
    assert out, 'must keep at least one tool call'
    # Must be parseable JSON (whole or reset to {}), never a sliced fragment.
    json.loads(out[0]['function']['arguments'])


def test_truncate_drops_whole_calls_before_gutting():
    a = {'id': 'c1', 'type': 'function', 'function': {'name': 'f', 'arguments': json.dumps({'x': 'a' * 200})}}
    b = {'id': 'c2', 'type': 'function', 'function': {'name': 'g', 'arguments': json.dumps({'y': 'b' * 200})}}
    out = truncate_tool_calls([a, b], 320)
    assert 1 <= len(out) <= 2
    for tc in out:
        json.loads(tc['function']['arguments'])  # every remaining call stays valid


def test_realistic_tool_call_passes_through_whole():
    args = json.dumps({'path': 'main.py', 'content': 'print("hello")\n' * 300})  # ~5 KB
    assert len(args) < proxy_max_response_chars()
    calls = [{'id': 'c1', 'type': 'function', 'function': {'name': 'write_file', 'arguments': args}}]
    out = truncate_tool_calls(calls, proxy_max_response_chars())
    assert out[0]['function']['arguments'] == args  # unchanged, not gutted


def test_cap_openai_chat_response_tool_calls_remain_valid_json():
    huge = json.dumps({'pattern': 'x' * 300_000})
    body = {'choices': [{'index': 0, 'message': {
        'role': 'assistant', 'content': '',
        'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'grep', 'arguments': huge}}],
    }, 'finish_reason': 'tool_calls'}]}
    out, _meta = cap_openai_chat_response(body)
    calls = out['choices'][0]['message']['tool_calls']
    assert calls
    json.loads(calls[0]['function']['arguments'])  # valid JSON, not a fragment


def test_stream_tool_call_arguments_stay_valid_json(monkeypatch):
    """Even with a tiny char budget, streamed tool_call arguments must parse as JSON."""
    monkeypatch.setenv('OLLAMA_PROXY_MAX_RESPONSE_CHARS', '2048')
    huge = 'x' * 50_000
    lines = [
        b'{"message":{"role":"assistant","tool_calls":[{"id":"c1","function":'
        b'{"name":"grep","arguments":{"pattern":"' + huge.encode() + b'"}}}],"content":""},'
        b'"done":true}',
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='qwen3:14b', omit_reasoning_deltas=True, agent_mode=True,
    ))
    assert '"tool_calls"' in out
    emitted = list(_iter_stream_tool_call_arguments(out))
    assert emitted, 'expected at least one tool_call arguments payload'
    for args in emitted:
        json.loads(args)  # must not raise


def test_stream_realistic_tool_call_arguments_preserved():
    args_obj = {'path': 'a.py', 'content': 'x = 1\n' * 200}
    lines = [
        json.dumps({'message': {'role': 'assistant', 'content': '',
                                 'tool_calls': [{'id': 'c1', 'function': {'name': 'write', 'arguments': args_obj}}]},
                    'done': True}).encode(),
    ]
    out = ''.join(stream_native_chat_lines_to_openai_sse(
        iter(lines), model='qwen3:14b', omit_reasoning_deltas=True, agent_mode=True,
    ))
    emitted = list(_iter_stream_tool_call_arguments(out))
    assert emitted
    # The full argument object must survive (not be gutted to {}).
    assert json.loads(emitted[0]) == args_obj


# --------------------------------------------------------------------------- #
# Agent-aware num_predict ceiling
# --------------------------------------------------------------------------- #
def test_num_predict_agent_allows_more_than_plain_chat():
    plain, _ = cap_num_predict({'max_tokens': 16_000, 'options': {}})
    assert plain['options']['num_predict'] == 8192  # plain-chat ceiling (capable models)
    agent, meta = cap_num_predict({'max_tokens': 16_000, 'options': {}}, agent=True)
    assert agent['options']['num_predict'] == 16_000
    assert meta['num_predict_ceiling'] >= 16_000


def test_num_predict_agent_ignores_small_saved_default():
    agent, _ = cap_num_predict({'options': {}}, {'num_predict': 512}, agent=True)
    assert agent['options']['num_predict'] > 512


def test_prepare_copilot_payload_uses_agent_ceiling_when_tools_present():
    payload = {
        'model': 'qwen3:14b',
        'messages': [{'role': 'user', 'content': 'edit my file'}],
        'tools': [{'type': 'function', 'function': {'name': 'write_file', 'parameters': {}}}],
        'max_tokens': 20_000,
    }
    merged, meta = prepare_copilot_payload(payload, None)
    assert merged['options']['num_predict'] == 20_000
    assert meta['client_compat'].get('agent') is True


# --------------------------------------------------------------------------- #
# Reasoning toggle resolves from the ORIGINAL payload (sanitize strips it)
# --------------------------------------------------------------------------- #
def test_reasoning_toggle_dead_without_env_default():
    native = openai_chat_to_native({'model': 'qwen3:14b', 'messages': [{'role': 'user', 'content': 'hi'}]}, {})
    apply_copilot_native_defaults(native, {'model': 'qwen3:14b', 'messages': [], 'reasoning_effort': 'high'})
    assert native['think'] is False  # off by default for plain chat


def test_reasoning_toggle_enabled_via_env_uses_original_payload(monkeypatch):
    monkeypatch.setenv('OLLAMA_COPILOT_ALLOW_THINKING', 'true')
    original = {'model': 'qwen3:14b', 'messages': [{'role': 'user', 'content': 'hi'}], 'reasoning_effort': 'high'}
    merged, _ = prepare_copilot_payload(original, None)
    # The trap: sanitize strips reasoning fields from the merged payload...
    assert 'reasoning_effort' not in merged
    native = openai_chat_to_native(merged, {})
    # ...so the route must resolve think from the ORIGINAL payload (this is the fix).
    apply_copilot_native_defaults(native, original)
    assert native.get('think') == 'high'


# --------------------------------------------------------------------------- #
# Capability detection repairs + MoE
# --------------------------------------------------------------------------- #
def test_api_capabilities_do_not_force_reasoning_false():
    """deepseek-r1 reporting only completion/tools must still be reasoning-capable."""
    model = ensure_capability_flags({'name': 'deepseek-r1:8b', 'capabilities': ['completion', 'tools']})
    assert model['has_reasoning'] is True
    assert model['has_tools'] is True


def test_api_capabilities_still_definitive_for_vision():
    model = ensure_capability_flags({'name': 'llava:7b', 'capabilities': ['completion']})
    assert model['has_vision'] is False  # API is authoritative: no vision alias => False


def test_family_defaults_fill_vision_gaps():
    assert detect_capabilities('gemma3:4b', [])['has_vision'] is True
    assert detect_capabilities('minicpm-v:8b', [])['has_vision'] is True
    assert detect_capabilities('mistral-small3.1:24b', [])['has_vision'] is True


def test_gpt_oss_is_tools_reasoning_and_moe():
    caps = detect_capabilities('gpt-oss:20b', [])
    assert caps['has_tools'] is True
    assert caps['has_reasoning'] is True
    assert caps['has_moe'] is True


@pytest.mark.parametrize('name', ['mixtral:8x7b', 'qwen3:30b-a3b', 'llama4:scout', 'gpt-oss:120b'])
def test_moe_detection_true(name):
    assert detect_capabilities(name, [])['has_moe'] is True


@pytest.mark.parametrize('name', ['llama3.1:8b', 'qwen3:8b', 'gemma3:4b', 'deepseek-r1:8b'])
def test_moe_detection_not_flagged_for_dense(name):
    assert detect_capabilities(name, [])['has_moe'] is False


def test_qwen3_vl_not_reasoning_after_changes():
    """Guard: family defaults / new heuristics must not flip qwen3-vl to reasoning."""
    caps = detect_capabilities('qwen3-vl:8b', [])
    assert caps['has_vision'] is True
    assert caps['has_tools'] is True
    assert caps['has_reasoning'] in (False, None)


def test_normalize_preserves_provider_capabilities_array():
    class _Svc:
        def format_size(self, size):
            return str(size)

    entry = {'name': 'somemystery-model:7b', 'capabilities': ['completion', 'vision', 'tools']}
    out = normalize_available_model_entry(_Svc(), entry)
    assert out['has_vision'] is True
    assert out['has_tools'] is True


# --------------------------------------------------------------------------- #
# Unreachable Ollama -> OpenAI-shaped error (not an HTML 500)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client(monkeypatch):
    from app import create_app
    app = create_app()
    return app.test_client()


def test_unreachable_ollama_returns_json_error(client, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise requests.ConnectionError('connection refused')

    monkeypatch.setattr('app.routes.proxy._upstream_request', _raise)
    resp = client.get('/ollama/v1/models')
    assert resp.status_code == 502
    assert resp.is_json
    body = resp.get_json()
    assert 'error' in body
    assert 'Ollama' in body['error']['message']
