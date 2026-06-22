"""Tests for read-only web tools."""
import json
from unittest.mock import MagicMock

import pytest
from app import create_app
from app.services import mcp_tools, web_tools


@pytest.fixture
def app_ctx():
    app = create_app()
    with app.app_context():
        yield app


def test_mcp_tools_include_web_by_default(app_ctx):
    names = {t['name'] for t in mcp_tools.list_tools_metadata()}
    assert 'fetch_url' in names
    assert 'web_search' in names


def test_mcp_tools_exclude_web_when_disabled(app_ctx, monkeypatch):
    monkeypatch.setenv('MCP_ALLOW_WEB', 'false')
    names = {t['name'] for t in mcp_tools.list_tools_metadata()}
    assert 'fetch_url' not in names
    assert 'web_search' not in names


def test_execute_web_tool_gated(app_ctx, monkeypatch):
    monkeypatch.setenv('MCP_ALLOW_WEB', 'false')
    result = json.loads(mcp_tools.execute_tool('fetch_url', {'url': 'https://example.com'}))
    assert 'error' in result


def test_validate_public_http_url_blocks_localhost():
    with pytest.raises(ValueError, match='blocked'):
        web_tools._validate_public_http_url('http://127.0.0.1/')


def test_validate_public_http_url_blocks_private_resolution(monkeypatch):
    monkeypatch.setattr(web_tools, '_resolve_host_ips', lambda _host: ['127.0.0.1'])
    with pytest.raises(ValueError, match='private'):
        web_tools._validate_public_http_url('https://example.com/')


def test_fetch_url_extracts_html_text(monkeypatch):
    monkeypatch.setattr(
        web_tools,
        '_validate_public_http_url',
        lambda url: url,
    )
    response = MagicMock()
    response.url = 'https://example.com/'
    response.status_code = 200
    response.headers = {'Content-Type': 'text/html; charset=utf-8'}
    response.iter_content = lambda chunk_size=8192: iter([b'<html><body><p>Hello web</p></body></html>'])
    response.raise_for_status = MagicMock()

    session = MagicMock()
    session.get.return_value = response
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(web_tools, '_session', lambda: session)

    result = web_tools.fetch_url({'url': 'https://example.com/'})
    assert result['text'] == 'Hello web'
    assert result['status_code'] == 200


def test_web_search_requires_query():
    result = web_tools.web_search({})
    assert result['error'] == 'query is required'


def test_parse_ddg_html_results():
    html_doc = """
    <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">
      Example title
    </a>
    """
    results = web_tools._parse_ddg_html_results(html_doc, 5)
    assert len(results) == 1
    assert results[0]['title'] == 'Example title'
    assert results[0]['url'] == 'https://example.com'
