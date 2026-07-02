"""Tests for Ask? agent tool loop."""
import json
from unittest.mock import MagicMock, patch

import pytest
from app.services.ask_agent import _AGENT_MAX_TEMPERATURE, _build_native_payload, stream_ask_agent


def _chat_response_lines(content='', tool_calls=None, done=True):
    message = {'role': 'assistant', 'content': content}
    if tool_calls:
        message['tool_calls'] = tool_calls
    return json.dumps({'message': message, 'done': done})


class _FakeStreamResponse:
    def __init__(self, lines):
        self.status_code = 200
        self._lines = lines

    def iter_lines(self):
        yield from self._lines

    def close(self):
        """No-op, matching requests.Response's interface (ask_agent always closes the
        upstream connection when done streaming a turn)."""


@pytest.fixture
def mock_session():
    session = MagicMock()
    return session


def test_agent_stream_final_content(mock_session):
    mock_session.post.return_value = _FakeStreamResponse([
        _chat_response_lines('Hello from agent'),
    ])

    lines = list(stream_ask_agent(
        session=mock_session,
        chat_url='http://localhost:11434/api/chat',
        model_name='qwen3:4b',
        messages=[{'role': 'user', 'content': 'Hi'}],
        options={},
        allow_write=False,
    ))
    events = [json.loads(line) for line in lines if line.strip()]
    assert events[0]['type'] == 'status'
    content_events = [e for e in events if e['type'] == 'content']
    assert content_events[0]['text'] == 'Hello from agent'
    assert events[-1]['type'] == 'done'


def test_agent_stream_executes_tool_then_answers(mock_session):
    tool_calls = [{
        'id': 'call_1',
        'type': 'function',
        'function': {
            'name': 'list_running_models',
            'arguments': '{}',
        },
    }]
    responses = [
        _FakeStreamResponse([_chat_response_lines('', tool_calls=tool_calls)]),
        _FakeStreamResponse([_chat_response_lines('Two models are running.')]),
    ]
    mock_session.post.side_effect = responses

    with patch('app.services.ask_agent.execute_tool', return_value='{"models":[]}') as exec_tool:
        lines = list(stream_ask_agent(
            session=mock_session,
            chat_url='http://localhost:11434/api/chat',
            model_name='qwen3:4b',
            messages=[{'role': 'user', 'content': 'What is running?'}],
            options={},
            allow_write=False,
        ))

    exec_tool.assert_called_once_with('list_running_models', {}, allow_write=False)
    events = [json.loads(line) for line in lines if line.strip()]
    types = [e['type'] for e in events]
    assert 'tool_call' in types
    assert 'tool_result' in types
    assert 'content' in types
    assert events[-1]['type'] == 'done'


def test_agent_breaks_on_repeated_tool_calls(mock_session):
    """A model that asks for the exact same tool call forever is stopped (no infinite loop)."""
    tool_calls = [{
        'id': 'call_loop',
        'type': 'function',
        'function': {'name': 'get_system_stats', 'arguments': '{}'},
    }]
    mock_session.post.side_effect = [
        _FakeStreamResponse([_chat_response_lines('', tool_calls=tool_calls)]) for _ in range(8)
    ]

    with patch('app.services.ask_agent.execute_tool', return_value='{"ok": true}') as exec_tool:
        lines = list(stream_ask_agent(
            session=mock_session,
            chat_url='http://localhost:11434/api/chat',
            model_name='qwen3:4b',
            messages=[{'role': 'user', 'content': 'loop please'}],
            options={},
            allow_write=False,
        ))

    events = [json.loads(line) for line in lines if line.strip()]
    assert events[-1]['type'] == 'error'
    assert 'repeated the same tool call' in events[-1]['message']
    # Stopped at the repeat threshold (3) instead of running all 8 iterations.
    assert exec_tool.call_count == 2


def test_agent_breaks_on_consecutive_tool_errors(mock_session):
    """Tools failing every turn stops the agent instead of looping to the iteration cap."""
    def resp_for(i):
        tc = [{
            'id': f'c{i}',
            'type': 'function',
            'function': {'name': 'get_model_info', 'arguments': json.dumps({'model_name': f'm{i}'})},
        }]
        return _FakeStreamResponse([_chat_response_lines('', tool_calls=tc)])

    mock_session.post.side_effect = [resp_for(i) for i in range(8)]

    with patch('app.services.ask_agent.execute_tool', return_value='{"error": "boom"}'):
        lines = list(stream_ask_agent(
            session=mock_session,
            chat_url='http://localhost:11434/api/chat',
            model_name='qwen3:4b',
            messages=[{'role': 'user', 'content': 'do it'}],
            options={},
            allow_write=False,
        ))

    events = [json.loads(line) for line in lines if line.strip()]
    assert events[-1]['type'] == 'error'
    assert 'turns in a row' in events[-1]['message']


def test_agent_stream_closes_upstream_response_after_turn(mock_session):
    """The upstream /api/chat response must always be closed after a turn — this is what
    lets a client-side Stop (abort) actually cancel in-flight Ollama generation instead of
    letting it keep running server-side."""
    response = _FakeStreamResponse([_chat_response_lines('done talking')])
    close_calls = []
    response.close = lambda: close_calls.append(True)
    mock_session.post.return_value = response

    list(stream_ask_agent(
        session=mock_session,
        chat_url='http://localhost:11434/api/chat',
        model_name='qwen3:4b',
        messages=[{'role': 'user', 'content': 'Hi'}],
        options={},
        allow_write=False,
    ))

    assert close_calls == [True]


def test_agent_stream_unexpected_error_yields_clean_error_event(mock_session):
    """An unexpected exception mid-loop must surface as a normal NDJSON error event, not a
    silently truncated/hung stream."""
    mock_session.post.side_effect = ValueError('boom: unexpected failure')

    lines = list(stream_ask_agent(
        session=mock_session,
        chat_url='http://localhost:11434/api/chat',
        model_name='qwen3:4b',
        messages=[{'role': 'user', 'content': 'Hi'}],
        options={},
        allow_write=False,
    ))

    events = [json.loads(line) for line in lines if line.strip()]
    assert events[-1]['type'] == 'error'
    assert 'Unexpected error' in events[-1]['message']


def test_build_native_payload_caps_high_temperature_for_tool_reliability():
    """A saved per-model temperature tuned for creative chat must not carry over unbounded
    into agent/tool-calling turns, where it makes malformed tool-call JSON more likely."""
    native = _build_native_payload('qwen3:4b', [{'role': 'user', 'content': 'hi'}], {'temperature': 0.9}, allow_write=False)
    assert native['options']['temperature'] == _AGENT_MAX_TEMPERATURE


def test_build_native_payload_keeps_low_temperature_as_is():
    native = _build_native_payload('qwen3:4b', [{'role': 'user', 'content': 'hi'}], {'temperature': 0.1}, allow_write=False)
    assert native['options']['temperature'] == 0.1


def test_build_native_payload_defaults_missing_temperature():
    native = _build_native_payload('qwen3:4b', [{'role': 'user', 'content': 'hi'}], {}, allow_write=False)
    assert native['options']['temperature'] == _AGENT_MAX_TEMPERATURE
