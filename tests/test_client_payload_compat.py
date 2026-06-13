"""Tests for external client payload compatibility."""
from app.services.client_payload_compat import (
    cap_num_predict,
    cap_openai_chat_response,
    prepare_external_v1_payload,
    sanitize_v1_chat_payload,
)
from app.services.v1_native_bridge import openai_chat_to_native


def test_sanitize_strips_unsupported_openai_fields():
    payload = {
        'model': 'qwen3:14b',
        'messages': [{'role': 'user', 'content': 'hi'}],
        'stream': True,
        'parallel_tool_calls': True,
        'store': False,
        'user': 'vscode',
        'max_completion_tokens': 8192,
    }
    out, meta = sanitize_v1_chat_payload(payload)
    assert out['max_tokens'] == 8192
    assert meta.get('mapped_max_completion_tokens') is True
    assert 'parallel_tool_calls' not in out
    assert 'store' not in out
    assert 'user' not in out


def test_cap_num_predict_limits_client_and_dashboard():
    payload = {'max_tokens': 32000, 'options': {}}
    capped, meta = cap_num_predict(payload, {'num_predict': 8192})
    assert capped['max_tokens'] == 4096
    assert capped['options']['num_predict'] == 4096
    assert meta['num_predict_ceiling'] == 4096


def test_cap_num_predict_respects_lower_saved_value():
    payload = {'options': {}}
    capped, _meta = cap_num_predict(payload, {'num_predict': 256})
    assert capped['options']['num_predict'] == 256


def test_prepare_external_v1_payload_sanitizes_and_caps():
    payload = {
        'model': 'm',
        'messages': [{'role': 'user', 'content': 'x'}],
        'max_completion_tokens': 50000,
        'metadata': {'trace': '1'},
    }
    out, meta = prepare_external_v1_payload(payload, None)
    assert out['max_tokens'] == 4096
    assert 'metadata' not in out
    assert meta['num_predict_capped'] == 4096


def test_sanitize_converts_multimodal_content_to_ollama_format():
    """Copilot sends content arrays; Ollama native /api/chat requires content: string + images[]."""
    b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
    payload = {
        'model': 'qwen3-vl:8b',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'What is in this image?'},
                {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
            ],
        }],
        'stream': True,
    }
    out, _meta = sanitize_v1_chat_payload(payload)
    msg = out['messages'][0]
    assert isinstance(msg['content'], str)
    assert msg['content'] == 'What is in this image?'
    assert msg['images'] == [b64]


def test_sanitize_image_only_message_gets_default_prompt():
    b64 = 'abc123'
    payload = {
        'model': 'qwen3-vl:8b',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{b64}'}},
            ],
        }],
    }
    out, _meta = sanitize_v1_chat_payload(payload)
    msg = out['messages'][0]
    assert isinstance(msg['content'], str)
    assert msg['content']
    assert msg['images'] == [b64]


def test_openai_chat_to_native_preserves_ollama_images():
    payload = {
        'model': 'qwen3-vl:8b',
        'messages': [{
            'role': 'user',
            'content': 'What is this?',
            'images': ['abc123'],
        }],
    }
    native = openai_chat_to_native(payload, {})
    assert native['messages'][0]['images'] == ['abc123']
    assert native['messages'][0]['content'] == 'What is this?'


def test_sanitize_maps_developer_role_to_system():
    payload = {
        'model': 'qwen3:14b',
        'messages': [{'role': 'developer', 'content': 'Be concise.'}],
    }
    out, _meta = sanitize_v1_chat_payload(payload)
    assert out['messages'][0]['role'] == 'system'
    assert out['messages'][0]['content'] == 'Be concise.'


def test_sanitize_assistant_tool_calls_get_empty_content():
    payload = {
        'model': 'qwen3:14b',
        'messages': [{
            'role': 'assistant',
            'tool_calls': [{
                'id': 'call_1',
                'type': 'function',
                'function': {'name': 'read_file', 'arguments': '{}'},
            }],
        }],
    }
    out, _meta = sanitize_v1_chat_payload(payload)
    msg = out['messages'][0]
    assert msg['role'] == 'assistant'
    assert msg['content'] == ''
    assert msg['tool_calls']


def test_sanitize_copilot_input_text_and_input_image():
    """VS Code Copilot BYOK uses input_text / input_image content block types."""
    b64 = 'imgdata456'
    payload = {
        'model': 'qwen3-vl:8b',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'input_text', 'text': 'Describe this screenshot'},
                {'type': 'input_image', 'image_url': f'data:image/png;base64,{b64}'},
            ],
        }],
    }
    out, _meta = sanitize_v1_chat_payload(payload)
    msg = out['messages'][0]
    assert msg['content'] == 'Describe this screenshot'
    assert msg['images'] == [b64]


def test_sanitize_anthropic_image_source_format():
    payload = {
        'model': 'qwen3-vl:8b',
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'Describe'},
                {
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': 'image/png',
                        'data': 'pngdata123',
                    },
                },
            ],
        }],
    }
    out, _meta = sanitize_v1_chat_payload(payload)
    msg = out['messages'][0]
    assert msg['images'] == ['pngdata123']
    assert msg['content'] == 'Describe'


def test_sanitize_tool_call_arguments_string_to_object():
    payload = {
        'model': 'qwen3:14b',
        'messages': [{
            'role': 'assistant',
            'content': '',
            'tool_calls': [{
                'id': 'call_1',
                'type': 'function',
                'function': {'name': 'calc', 'arguments': '{"expr":"2+2"}'},
            }],
        }],
    }
    out, _meta = sanitize_v1_chat_payload(payload)
    args = out['messages'][0]['tool_calls'][0]['function']['arguments']
    assert args == {'expr': '2+2'}


def test_sanitize_function_role_maps_to_tool():
    payload = {
        'model': 'm',
        'messages': [{'role': 'function', 'name': 'get_weather', 'content': 'sunny'}],
    }
    out, _meta = sanitize_v1_chat_payload(payload)
    assert out['messages'][0]['role'] == 'tool'


def test_cap_openai_chat_response_preserves_tool_calls():
    body = {
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': 'x' * 200_000,
                'reasoning': 'y' * 10_000,
                'tool_calls': [{
                    'id': 'call_1',
                    'type': 'function',
                    'function': {'name': 'f', 'arguments': '{}'},
                }],
            },
            'finish_reason': 'tool_calls',
        }],
    }
    out, meta = cap_openai_chat_response(body)
    assert meta['truncated'] is True
    assert out['choices'][0]['message']['tool_calls']


def test_cap_openai_chat_response_truncates_huge_content():
    body = {
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': 'x' * 200_000,
                'reasoning': 'y' * 10_000,
            },
            'finish_reason': 'stop',
        }],
    }
    out, meta = cap_openai_chat_response(body)
    assert meta['truncated'] is True
    content = out['choices'][0]['message']['content']
    assert len(content) < 200_000
    assert 'truncated by ollama-dashboard proxy' in content
