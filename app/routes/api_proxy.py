"""External API proxy — status, setup wizard, analytics, RAG routes."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from app.services import mcp_tools
from app.services.copilot_analytics import client_proxy_analytics, client_proxy_status, read_log_records
from app.services.copilot_prewarm import schedule_context_preload
from app.services.mcp_server import mcp_health_check
from app.services.model_advisor import advise_from_hardware
from app.services.model_settings_helpers import lookup_settings_entry
from app.services.rag import index_workspace, rag_status
from app.services.settings_cache import load_settings_file

logger = logging.getLogger(__name__)

bp = Blueprint('api_proxy_api', __name__)


def _svc():
    return current_app.config['OLLAMA_SERVICE']


def _ollama_url():
    host, port = _svc().get_ollama_host_port()
    return f'http://{host}:{port}'


def _data_dir():
    return current_app.config.get('DATA_DIR') or 'data'


def _proxy_base():
    return request.host_url.rstrip('/') + '/ollama'


def _mcp_base():
    return request.host_url.rstrip('/') + '/mcp'


def _mcp_client_examples(mcp_url: str, proxy_url: str) -> list[dict[str, str]]:
    cursor_json = json.dumps(
        {'mcpServers': {'ollama-dashboard': {'url': mcp_url}}},
        indent=2,
    )
    vscode_json = json.dumps(
        {'servers': {'ollama-dashboard': {'type': 'http', 'url': mcp_url}}},
        indent=2,
    )
    return [
        {
            'name': 'Cursor — MCP tools',
            'field': '.cursor/mcp.json',
            'value': cursor_json,
            'hint': 'Adds dashboard tools (models, stats, proxy status). Use with Ollama proxy for chat.',
        },
        {
            'name': 'VS Code — MCP extension',
            'field': 'mcp.servers (settings JSON)',
            'value': vscode_json,
            'hint': 'Same MCP URL; pair with the Ollama provider URL (Chat: Manage Language Models) for models.',
        },
        {
            'name': 'Combined IDE setup',
            'field': 'Models + tools',
            'value': f'Ollama proxy: {proxy_url}  |  MCP tools: {mcp_url}',
            'hint': 'Proxy URL for LLM inference; MCP URL for dashboard tool access.',
        },
    ]


def _mcp_status_payload():
    health = mcp_health_check(current_app._get_current_object())
    mcp_url = _mcp_base()
    tools = mcp_tools.list_tools_metadata()
    return {
        'ok': bool(health.get('ok')),
        'mcp_base_url': mcp_url,
        'mcp_enabled': bool(health.get('ok')),
        'tool_count': len(tools),
        'write_tools_enabled': mcp_tools.mcp_allow_write(),
        'tools': tools,
        'health': health,
    }


def _client_examples(base: str) -> list[dict[str, str]]:
    """Example configuration snippets for common compatible clients."""
    openai_v1 = base.rstrip('/') + '/v1'
    return [
        {
            'name': 'Any Ollama-compatible app (server address)',
            'field': 'Ollama host / server URL',
            'value': base,
            'hint': 'Use this wherever the app asks for the Ollama server — not :11434 directly.',
        },
        {
            'name': 'OpenAI-compatible SDK (GPT-style clients)',
            'field': 'base_url',
            'value': openai_v1,
            'hint': 'For libraries that expect https://api.openai.com/v1 — use chat.completions.',
        },
        {
            'name': 'VS Code — Copilot Chat (Ollama provider)',
            'field': 'Chat: Manage Language Models → Ollama',
            'value': base,
            'hint': 'VS Code 1.122+: add an Ollama provider with this URL (stored in '
                    'chatLanguageModels.json), or run scripts/setup_vscode.py. Do not add /v1.',
        },
        {
            'name': 'Continue extension',
            'field': 'apiBase',
            'value': base,
            'hint': 'In config.jsonc: provider "ollama", apiBase as shown.',
        },
        {
            'name': 'Claude Code / other IDE agents using Ollama',
            'field': 'Ollama / model server URL',
            'value': base,
            'hint': 'Same proxy URL wherever the tool asks for Ollama instead of localhost:11434.',
        },
    ]


def _status_payload():
    status = client_proxy_status(_data_dir(), ollama_base_url=_ollama_url())
    base = _proxy_base()
    status['proxy_base_url'] = base
    status['proxy_endpoint'] = base  # legacy key
    status['ok'] = True
    return status


def _wizard_payload():
    checks = []
    base = _proxy_base()

    def add(name, passed, detail, fix=None):
        checks.append({'name': name, 'passed': passed, 'detail': detail, 'fix': fix})

    try:
        client = current_app.test_client()
        r_root = client.get('/ollama')
        add('proxy_root', r_root.status_code == 200, f'GET /ollama → {r_root.status_code}',
            None if r_root.status_code == 200 else 'Restart the dashboard.')
        r_models = client.get('/ollama/v1/models')
        body_ok = r_models.status_code == 200 and r_models.is_json
        add('openai_models', body_ok, f'GET /ollama/v1/models → {r_models.status_code}',
            None if body_ok else f'Point the app at {base}')
        r_tags = client.get('/ollama/api/tags')
        tags_ok = r_tags.status_code == 200 and r_tags.is_json
        add('ollama_api_tags', tags_ok, f'GET /ollama/api/tags → {r_tags.status_code}')
        svc_ok = _svc().get_service_status()
        add('ollama_running', svc_ok, 'Ollama HTTP API reachable' if svc_ok else 'Start Ollama service')
    except (RuntimeError, OSError, ValueError, TypeError) as err:
        logger.exception('Proxy wizard self-check failed')
        add('internal', False, str(err))

    add('proxy_url', True, f'Use {base} as the server / API base in your app', f'Copy: {base}')

    mcp_url = _mcp_base()
    mcp_health = mcp_health_check(current_app._get_current_object())
    add(
        'mcp_endpoint',
        bool(mcp_health.get('ok')),
        f'MCP tools at {mcp_url} ({mcp_health.get("tool_count", 0)} tools)',
        None if mcp_health.get('ok') else 'Install mcp and a2wsgi, then restart the dashboard.',
    )

    passed = all(c['passed'] for c in checks if c['name'] not in ('proxy_url',))
    mcp_status = _mcp_status_payload()
    return {
        'success': passed,
        'checks': checks,
        'proxy_base_url': base,
        'proxy_endpoint': base,
        'client_examples': _client_examples(base),
        'mcp_base_url': mcp_url,
        'mcp_enabled': mcp_status.get('mcp_enabled'),
        'mcp_tools': mcp_status.get('tools') or [],
        'mcp_write_tools_enabled': mcp_status.get('write_tools_enabled'),
        'mcp_client_examples': _mcp_client_examples(mcp_url, base),
    }


@bp.route('/api/proxy/status')
@bp.route('/api/copilot/status')  # legacy
def api_proxy_status():
    """Lightweight proxy activity for the dashboard header."""
    try:
        return jsonify(_status_payload())
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as err:
        logger.exception('Proxy status endpoint failed')
        return jsonify({'ok': False, 'error': str(err)}), 500


@bp.route('/api/proxy/wizard-checks')
@bp.route('/api/copilot/wizard-checks')  # legacy
def api_proxy_wizard_checks():
    """Run setup checks for external OpenAI/Ollama-compatible clients."""
    return jsonify(_wizard_payload())


@bp.route('/api/mcp/status')
def api_mcp_status():
    """MCP server status for Connect panel and health checks."""
    try:
        return jsonify(_mcp_status_payload())
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as err:
        logger.exception('MCP status endpoint failed')
        return jsonify({'ok': False, 'error': str(err)}), 500


@bp.route('/api/proxy/analytics')
@bp.route('/api/copilot/analytics')  # legacy
def api_proxy_analytics():
    return jsonify(client_proxy_analytics(_data_dir()))


@bp.route('/api/proxy/debug-requests')
@bp.route('/api/copilot/debug-requests')  # legacy
def api_proxy_debug_requests():
    try:
        limit = min(int(request.args.get('limit', 20)), 100)
    except (TypeError, ValueError):
        limit = 20
    records = read_log_records(_data_dir(), limit=500)
    chat = [r for r in records if r.get('model_in') or r.get('model_resolved')]
    return jsonify({'requests': chat[-limit:], 'total': len(chat)})


@bp.route('/api/proxy/prewarm', methods=['POST'])
@bp.route('/api/copilot/prewarm', methods=['POST'])  # legacy
def api_proxy_prewarm():
    """Background-preload a model with saved context (non-blocking)."""
    body = request.get_json(silent=True) or {}
    model_name = (body.get('model') or '').strip()
    if not model_name:
        return jsonify({'success': False, 'error': 'model required'}), 400
    entry = _svc().get_model_settings_with_fallback(model_name) or {}
    options = entry.get('settings') or {}
    schedule_context_preload(_ollama_url(), model_name, options)
    return jsonify({'success': True, 'message': f'Preload scheduled for {model_name}'})


@bp.route('/api/advisor/recommend')
def api_advisor_recommend():
    """Hardware-based model/context recommendations."""
    stats = _svc().get_system_stats()
    vram = stats.get('vram') or {}
    mem = stats.get('memory') or {}
    vram_mb = (vram.get('total') or 0) / (1024 * 1024) if vram.get('total') else 0
    ram_mb = (mem.get('total') or 0) / (1024 * 1024) if mem.get('total') else 8192
    model = request.args.get('model')
    rec = advise_from_hardware(
        vram_total_mb=vram_mb,
        ram_total_mb=ram_mb,
        model_name=model,
    )
    rec['proxy_base_url'] = _proxy_base()
    return jsonify(rec)


@bp.route('/api/models/settings/export')
def api_export_settings():
    path = Path(current_app.config['MODEL_SETTINGS_FILE'])
    if not path.is_file():
        return jsonify({'settings': {}})
    data = load_settings_file(path)
    model = request.args.get('model')
    if model:
        entry = lookup_settings_entry(data, model)
        return jsonify({'model': model, 'entry': entry})
    return jsonify({'settings': data})


@bp.route('/api/models/settings/import', methods=['POST'])
def api_import_settings():
    body = request.get_json(silent=True) or {}
    entries = body.get('settings') if isinstance(body.get('settings'), dict) else body
    if not isinstance(entries, dict) or not entries:
        return jsonify({'success': False, 'error': 'settings object required'}), 400
    svc = _svc()
    imported = 0
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        settings = entry.get('settings')
        if not isinstance(settings, dict):
            continue
        client = entry.get('client') or entry.get('copilot')
        svc.save_model_settings(name, settings, source=entry.get('source', 'user'))
        if client:
            svc.save_model_client_extras(name, client)
        imported += 1
    return jsonify({'success': True, 'imported': imported})


@bp.route('/api/rag/status')
def api_rag_status():
    return jsonify(rag_status())


@bp.route('/api/rag/index', methods=['POST'])
def api_rag_index():
    if os.getenv('RAG_ENABLED', '').strip().lower() not in ('1', 'true', 'yes'):
        return jsonify({'success': False, 'error': 'RAG_ENABLED is not set'}), 400
    body = request.get_json(silent=True) or {}
    root = Path(body.get('root') or os.getenv('WORKSPACE_ROOT') or '.').resolve()
    if not root.is_dir():
        return jsonify({'success': False, 'error': f'Not a directory: {root}'}), 400
    result = index_workspace(root)
    return jsonify({'success': True, **result})
