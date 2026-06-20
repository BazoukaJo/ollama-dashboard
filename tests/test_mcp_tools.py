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
