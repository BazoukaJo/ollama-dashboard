#!/usr/bin/env python3
"""Point VS Code (GitHub Copilot Chat) at the Ollama Dashboard proxy.

On VS Code 1.122+ the supported BYOK path is the built-in **Ollama / Custom Endpoint**
provider, configured via *Chat: Manage Language Models*. VS Code stores those providers in a
``chatLanguageModels.json`` file next to ``settings.json``. This script adds an Ollama provider
entry that points at the dashboard proxy, so Copilot inherits saved per-model ``num_ctx``,
parameter sanitization, output caps, and the v1 -> ``/api/chat`` bridge (which is what stops
the "Sorry, no response was returned" empty replies).

It also applies a couple of context-reduction settings in ``settings.json`` so Agent mode
sends smaller payloads and large models answer before Copilot's built-in client timeout.

The legacy ``github.copilot.chat.byok.ollamaEndpoint`` setting is intentionally NOT used: it is
deprecated and silently removed on current VS Code builds.

Existing config is preserved (entries are added, settings only added or raised) and a
timestamped backup is written before any file changes.

Usage::

    python scripts/setup_vscode.py
    python scripts/setup_vscode.py --port 5000
    python scripts/setup_vscode.py --endpoint http://127.0.0.1:5000/ollama
    python scripts/setup_vscode.py --insiders          # target "VS Code - Insiders"
    python scripts/setup_vscode.py --user-dir "/custom/Code/User"
    python scripts/setup_vscode.py --dry-run           # show changes, write nothing

Restart VS Code (or run *Chat: Manage Language Models* -> the provider) after running.
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
PROVIDER_NAME = 'OllamaDashboard'
MIN_AGENT_MAX_REQUESTS = 50


def default_user_dir(insiders: bool = False) -> Path:
    """Best-effort location of the VS Code ``User`` config directory for this OS."""
    flavor = 'Code - Insiders' if insiders else 'Code'
    system = platform.system()
    if system == 'Windows':
        import os

        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(base) / flavor / 'User'
    if system == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / flavor / 'User'
    return Path.home() / '.config' / flavor / 'User'


def strip_jsonc(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments and trailing commas, string-aware.

    VS Code config files are JSON-with-comments (JSONC). ``json.loads`` rejects comments and
    trailing commas, so strip them without touching ``//`` or commas inside strings (for
    example the ``//`` in ``"http://..."``).
    """
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


def configure_models(models: list, endpoint: str) -> list[str]:
    """Add an Ollama provider pointing at ``endpoint`` if not already present."""
    target = endpoint.rstrip('/')
    for entry in models:
        if (
            isinstance(entry, dict)
            and str(entry.get('vendor', '')).lower() == 'ollama'
            and str(entry.get('url', '')).rstrip('/') == target
        ):
            return []
    models.append({'name': PROVIDER_NAME, 'vendor': 'ollama', 'url': endpoint})
    return [f'chatLanguageModels.json: added Ollama provider "{PROVIDER_NAME}" -> {endpoint}']


def configure_settings(settings: dict) -> list[str]:
    """Apply non-destructive context-reduction settings; return human-readable changes."""
    changes: list[str] = []

    key = 'chat.tools.compressOutput.enabled'
    if settings.get(key) is not True:
        settings[key] = True
        changes.append(f'settings.json: {key} = true')

    key = 'chat.agent.maxRequests'
    current = settings.get(key)
    if not isinstance(current, int) or current < MIN_AGENT_MAX_REQUESTS:
        settings[key] = MIN_AGENT_MAX_REQUESTS
        changes.append(f'settings.json: {key} = {MIN_AGENT_MAX_REQUESTS}')

    key = 'files.exclude'
    excludes = settings.get(key)
    if not isinstance(excludes, dict):
        excludes = {}
    for pattern in ('**/node_modules', '**/.venv', '**/data/*.log'):
        if excludes.get(pattern) is not True:
            excludes[pattern] = True
            changes.append(f'settings.json: {key}["{pattern}"] = true')
    settings[key] = excludes

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
        description='Point VS Code Copilot Chat at the Ollama Dashboard proxy.',
    )
    parser.add_argument('--endpoint', help='Dashboard proxy base URL (overrides --port).')
    parser.add_argument(
        '--port', type=int, default=DEFAULT_PORT,
        help=f'Dashboard port for the default endpoint (default {DEFAULT_PORT}).',
    )
    parser.add_argument('--user-dir', help='VS Code User directory (overrides OS auto-detect).')
    parser.add_argument(
        '--insiders', action='store_true', help='Target "VS Code - Insiders" instead of stable.',
    )
    parser.add_argument(
        '--dry-run', action='store_true', help='Print changes without writing files.',
    )
    args = parser.parse_args(argv)

    endpoint = args.endpoint or f'http://127.0.0.1:{args.port}/ollama'
    user_dir = Path(args.user_dir).expanduser() if args.user_dir else default_user_dir(args.insiders)
    models_path = user_dir / 'chatLanguageModels.json'
    settings_path = user_dir / 'settings.json'

    print(f'VS Code User dir: {user_dir}')
    print(f'Proxy endpoint:   {endpoint}\n')

    try:
        models, models_had_comments = load_jsonc(models_path, [])
        settings, settings_had_comments = load_jsonc(settings_path, {})
    except json.JSONDecodeError as err:
        print(f'ERROR: could not parse VS Code config as JSON/JSONC: {err}', file=sys.stderr)
        print('Fix the file manually or pass --user-dir. No changes were made.', file=sys.stderr)
        return 2

    if not isinstance(models, list):
        print(f'ERROR: {models_path} is not a JSON array.', file=sys.stderr)
        return 2
    if not isinstance(settings, dict):
        print(f'ERROR: {settings_path} is not a JSON object.', file=sys.stderr)
        return 2

    model_changes = configure_models(models, endpoint)
    settings_changes = configure_settings(settings)
    all_changes = model_changes + settings_changes

    if not all_changes:
        print('Already configured - no changes needed.')
        return 0

    print('Changes to apply:')
    for change in all_changes:
        print(f'  + {change}')
    print()

    if args.dry_run:
        print('--dry-run: nothing written.')
        return 0

    if model_changes:
        write_with_backup(models_path, models, models_had_comments, args.dry_run)
    if settings_changes:
        write_with_backup(settings_path, settings, settings_had_comments, args.dry_run)

    print('\nDone. Restart VS Code, then pick the "OllamaDashboard" model in Copilot Chat.')
    print('If models do not appear, run "Chat: Manage Language Models" and refresh the Ollama provider.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
