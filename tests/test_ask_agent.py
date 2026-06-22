"""Tests for Ask? agent tool loop."""
import json
from unittest.mock import MagicMock, patch

import pytest
from app.services.ask_agent import stream_ask_agent


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
