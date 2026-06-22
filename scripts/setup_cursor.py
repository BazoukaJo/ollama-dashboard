#!/usr/bin/env python3
"""Configure Cursor IDE for the Ollama Dashboard MCP server and optional model override.

Writes or merges ``.cursor/mcp.json`` with an HTTP MCP entry pointing at the dashboard's
embedded Streamable HTTP server (``http://127.0.0.1:<port>/mcp``). Dashboard MCP tools expose
model lists, system stats, proxy activity, and optional write actions without scraping the UI.

Optionally merges an OpenAI-compatible **Override Base URL** into project ``.vscode/settings.json``
(``--project``, default) or Cursor user ``settings.json`` (``--user``) so Chat/Agent can reach
``http://127.0.0.1:<port>/ollama/v1`` with saved per-model settings. Cursor may also require
enabling the override in **Cursor Settings → Models**; the script sets known settings keys as
a best-effort helper.

Existing config is preserved (entries are merged, not replaced) and a timestamped backup is
written before any file changes.

Usage::

    python scripts/setup_cursor.py
    python scripts/setup_cursor.py --port 5000
    python scripts/setup_cursor.py --user
    python scripts/setup_cursor.py --with-ollama-override
    python scripts/setup_cursor.py --dry-run

    # Project-scoped (default): repo/.cursor/mcp.json
    python scripts/setup_cursor.py --project

    # Global Cursor config: ~/.cursor/mcp.json (Windows: %USERPROFILE%\\.cursor\\mcp.json)
    python scripts/setup_cursor.py --user --with-ollama-override

Restart Cursor after running so MCP and model settings reload.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_PORT = 5000
MCP_SERVER_NAME = 'ollama-dashboard'
BASE_URL_KEYS = (
    'cursor.general.openAiBaseUrl',
    'cursor.openai.baseUrl',
)
API_KEY_KEYS = (
    'cursor.general.openAiApiKey',
    'cursor.openai.apiKey',
)
DEFAULT_API_KEY_PLACEHOLDER = 'ollama'


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_cursor_user_dir() -> Path:
    """Best-effort Cursor user config directory for this OS."""
    system = platform.system()
    if system == 'Windows':
        return Path.home() / '.cursor'
    if system == 'Darwin':
        return Path.home() / '.cursor'
    return Path.home() / '.cursor'


def cursor_user_settings_path() -> Path:
    system = platform.system()
    if system == 'Windows':
        import os

        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(base) / 'Cursor' / 'User' / 'settings.json'
    if system == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Cursor' / 'User' / 'settings.json'
    return Path.home() / '.config' / 'Cursor' / 'User' / 'settings.json'


def mcp_config_path(use_user: bool) -> Path:
    if use_user:
        return default_cursor_user_dir() / 'mcp.json'
    return repo_root() / '.cursor' / 'mcp.json'


def ollama_override_settings_path(use_user: bool) -> Path:
    if use_user:
        return cursor_user_settings_path()
    return repo_root() / '.vscode' / 'settings.json'


def strip_jsonc(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments and trailing commas, string-aware."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            i += 2
            while i < n and text[i] not in '\r\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            i += 2
            while i + 1 < n and not (text[i] == '*' and text[i + 1] == '/'):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1

    cleaned = ''.join(out)
    result: list[str] = []
    i, n = 0, len(cleaned)
    in_str = False
    while i < n:
        c = cleaned[i]
        if in_str:
            result.append(c)
            if c == '\\' and i + 1 < n:
                result.append(cleaned[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            result.append(c)
            i += 1
            continue
        if c == ',':
            j = i + 1
            while j < n and cleaned[j] in ' \t\r\n':
                j += 1
            if j < n and cleaned[j] in '}]':
                i += 1
                continue
        result.append(c)
        i += 1
    return ''.join(result)


def load_jsonc(path: Path, fallback):
    """Return (parsed, had_comments). Missing/empty file yields ``fallback``."""
    if not path.is_file():
        return fallback, False
    text = path.read_text(encoding='utf-8-sig')
    if not text.strip():
        return fallback, False
    try:
        return json.loads(text), False
    except json.JSONDecodeError:
        return json.loads(strip_jsonc(text)), True


def configure_mcp(config: dict, mcp_url: str) -> list[str]:
    """Add or update the dashboard MCP HTTP server entry."""
    if not isinstance(config, dict):
        config = {}
    servers = config.setdefault('mcpServers', {})
    if not isinstance(servers, dict):
        servers = {}
        config['mcpServers'] = servers

    target = mcp_url.rstrip('/')
    existing = servers.get(MCP_SERVER_NAME)
    if isinstance(existing, dict) and str(existing.get('url', '')).rstrip('/') == target:
        return []

    servers[MCP_SERVER_NAME] = {'url': mcp_url}
    return [f'mcp.json: set mcpServers.{MCP_SERVER_NAME}.url -> {mcp_url}']


def _set_if_different(settings: dict, key: str, value: str) -> str | None:
    if settings.get(key) == value:
        return None
    settings[key] = value
    return f'settings.json: {key} = {value!r}'


def configure_ollama_override(settings: dict, v1_url: str) -> list[str]:
    """Merge OpenAI-compatible override URL keys for Cursor Chat."""
    changes: list[str] = []
    for key in BASE_URL_KEYS:
        change = _set_if_different(settings, key, v1_url)
        if change:
            changes.append(change)

    for key in API_KEY_KEYS:
        current = settings.get(key)
        if isinstance(current, str) and current.strip():
            continue
        change = _set_if_different(settings, key, DEFAULT_API_KEY_PLACEHOLDER)
        if change:
            changes.append(change)

    return changes


def write_with_backup(path: Path, data, had_comments: bool, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup = path.with_name(f'{path.name}.bak-{stamp}')
        shutil.copy2(path, backup)
        print(f'  backup: {backup}')
        if had_comments:
            print('  note: comments are not preserved (restore from backup if needed).')
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'  wrote:  {path}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Configure Cursor MCP and optional Ollama Dashboard model override.',
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        '--project',
        action='store_true',
        help='Write repo .cursor/mcp.json (default when neither --project nor --user is given).',
    )
    scope.add_argument(
        '--user',
        action='store_true',
        help='Write global ~/.cursor/mcp.json instead of project config.',
    )
    parser.add_argument(
        '--port', type=int, default=DEFAULT_PORT,
        help=f'Dashboard port (default {DEFAULT_PORT}).',
    )
    parser.add_argument(
        '--with-ollama-override',
        action='store_true',
        help=(
            'Also merge OpenAI base URL into .vscode/settings.json (--project) or '
            'Cursor user settings.json (--user).'
        ),
    )
    parser.add_argument(
        '--dry-run', action='store_true', help='Print changes without writing files.',
    )
    args = parser.parse_args(argv)

    use_user = bool(args.user)
    mcp_url = f'http://127.0.0.1:{args.port}/mcp'
    v1_url = f'http://127.0.0.1:{args.port}/ollama/v1'
    mcp_path = mcp_config_path(use_user)

    scope_label = 'global (~/.cursor)' if use_user else f'project ({repo_root() / ".cursor"})'
    print(f'Config scope:   {scope_label}')
    print(f'MCP URL:        {mcp_url}')
    if args.with_ollama_override:
        settings_target = ollama_override_settings_path(use_user)
        print(f'Override URL:   {v1_url}')
        print(f'Settings file:  {settings_target}')
    print()

    try:
        mcp_config, mcp_had_comments = load_jsonc(mcp_path, {})
        mcp_changes = configure_mcp(mcp_config, mcp_url)

        settings_changes: list[str] = []
        settings_path = None
        settings_had_comments = False
        settings_data = {}
        if args.with_ollama_override:
            settings_path = ollama_override_settings_path(use_user)
            settings_data, settings_had_comments = load_jsonc(settings_path, {})
            if not isinstance(settings_data, dict):
                print(f'ERROR: {settings_path} is not a JSON object.', file=sys.stderr)
                return 2
            settings_changes = configure_ollama_override(settings_data, v1_url)
    except json.JSONDecodeError as err:
        print(f'ERROR: could not parse config as JSON/JSONC: {err}', file=sys.stderr)
        print('Fix the file manually or restore from a .bak-* backup. No changes were made.', file=sys.stderr)
        return 2

    all_changes = mcp_changes + settings_changes
    if not all_changes:
        print('Already configured — no changes needed.')
        return 0

    print('Changes to apply:')
    for change in all_changes:
        print(f'  + {change}')
    print()

    if args.dry_run:
        print('--dry-run: nothing written.')
        return 0

    if mcp_changes:
        write_with_backup(mcp_path, mcp_config, mcp_had_comments, args.dry_run)
    if settings_changes and settings_path is not None:
        write_with_backup(settings_path, settings_data, settings_had_comments, args.dry_run)

    print('\nDone. Restart Cursor.')
    print(f'MCP tools: {mcp_url}')
    if args.with_ollama_override:
        print(
            'Model override: enable "Override OpenAI Base URL" in Cursor Settings → Models '
            f'if Chat does not pick up {v1_url} automatically.'
        )
        print('Add your local model name(s) in Cursor Settings → Models and disable cloud models.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
