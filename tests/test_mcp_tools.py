"""Tests for MCP tool registry."""
import json
from unittest.mock import MagicMock, patch

import pytest
from app import create_app
from app.services import mcp_tools


@pytest.fixture
def app_ctx():
    app = create_app()
    with app.app_context():
        yield app


def test_list_tools_metadata_excludes_write_by_default(app_ctx):
    names = {t['name'] for t in mcp_tools.list_tools_metadata()}
    assert 'list_available_models' in names
    assert 'start_model' not in names
    assert 'stop_model' not in names


def test_list_tools_metadata_includes_write_when_enabled(app_ctx, monkeypatch):
    monkeypatch.setenv('MCP_ALLOW_WRITE', 'true')
    names = {t['name'] for t in mcp_tools.list_tools_metadata()}
    assert 'start_model' in names
    assert 'stop_model' in names


def test_execute_tool_unknown(app_ctx):
    result = json.loads(mcp_tools.execute_tool('not_a_tool', {}))
    assert 'error' in result


def test_execute_tool_write_gated(app_ctx, monkeypatch):
    monkeypatch.delenv('MCP_ALLOW_WRITE', raising=False)
    result = json.loads(mcp_tools.execute_tool('start_model', {'model_name': 'llama3.2:3b'}))
    assert 'error' in result


def test_execute_tool_missing_required_argument_fails_fast(app_ctx, monkeypatch):
    """A hallucinated tool call missing a required arg gets an actionable error, not a crash
    or a confusing downstream 'not found' from the handler."""
    monkeypatch.setenv('MCP_ALLOW_WRITE', 'true')
    result = json.loads(mcp_tools.execute_tool('get_model_info', {}))
    assert 'error' in result
    assert 'model_name' in result['error']


def test_execute_tool_wrong_argument_type_fails_fast(app_ctx):
    """A model passing a list/dict where a string was expected gets a clear type error
    instead of silently stringifying into something like \"['a', 'b']\" as a model name."""
    result = json.loads(mcp_tools.execute_tool('get_model_info', {'model_name': ['a', 'b']}))
    assert 'error' in result
    assert 'string' in result['error']


def test_execute_tool_well_formed_arguments_still_work(app_ctx):
    """Validation must not reject legitimate, well-formed calls."""
    with patch.object(mcp_tools, '_svc') as svc:
        svc.return_value.get_model_info_cached.return_value = {'name': 'llama3.2:3b'}
        result = json.loads(mcp_tools.execute_tool('get_model_info', {'model_name': 'llama3.2:3b'}))
    assert 'error' not in result
    assert result.get('name') == 'llama3.2:3b'


def test_get_tool_definitions_shape(app_ctx):
    tools = mcp_tools.get_tool_definitions()
    assert tools
    for tool in tools:
        assert tool['type'] == 'function'
        fn = tool['function']
        assert fn['name']
        assert fn['description']
        assert fn['parameters']['type'] == 'object'


def test_execute_list_available_models(app_ctx):
    mock_svc = MagicMock()
    mock_svc.get_available_models.return_value = [
        {'name': 'llama3.2:3b', 'has_tools': True, 'has_vision': False},
    ]
    with patch.object(mcp_tools, '_svc', return_value=mock_svc):
        result = json.loads(mcp_tools.execute_tool('list_available_models', {}))
    assert result['count'] == 1
    assert result['models'][0]['name'] == 'llama3.2:3b'
