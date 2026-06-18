#!/usr/bin/env python3
"""Live smoke test: Copilot-shaped chat + Agent tools through running dashboard proxy."""
from __future__ import annotations

import json
import sys

import requests

BASE = 'http://127.0.0.1:5000/ollama'
MODEL = 'qwen3.5:9b'
TIMEOUT = 180


def parse_sse(text: str) -> list[dict]:
    chunks: list[dict] = []
    for line in text.splitlines():
        if line.startswith('data: ') and line != 'data: [DONE]':
            try:
                chunks.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return chunks


def test_plain_chat() -> bool:
    payload = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': 'Reply with exactly: PROXY_OK'}],
        'stream': True,
        'reasoning_effort': 'medium',
    }
    r = requests.post(
        f'{BASE}/v1/chat/completions', json=payload, stream=True, timeout=TIMEOUT,
    )
    r.raise_for_status()
    chunks = parse_sse(r.text)
    content = ''.join(
        c['choices'][0]['delta'].get('content') or ''
        for c in chunks if c.get('choices')
    )
    reasoning = sum(
        1 for c in chunks
        if (c.get('choices') or [{}])[0].get('delta', {}).get('reasoning')
    )
    ok = 'PROXY_OK' in content and content.strip() != 'I'
    print('PLAIN_CHAT:', 'PASS' if ok else 'FAIL')
    print('  content:', repr(content[:120]))
    print('  reasoning_deltas:', reasoning)
    return ok


def test_agent_tools() -> bool:
    tools = [{
        'type': 'function',
        'function': {
            'name': 'read_file',
            'description': 'Read a file path',
            'parameters': {
                'type': 'object',
                'properties': {'path': {'type': 'string'}},
                'required': ['path'],
            },
        },
    }]
    payload = {
        'model': MODEL,
        'messages': [{
            'role': 'system',
            'content': 'You are a coding agent. Use tools when asked to read files.',
        }, {
            'role': 'user',
            'content': (
                'Use the read_file tool to read package.json. '
                'Do not answer in prose only — call the tool.'
            ),
        }],
        'tools': tools,
        'tool_choice': 'auto',
        'stream': True,
        'reasoning_effort': 'medium',
    }
    r = requests.post(
        f'{BASE}/v1/chat/completions', json=payload, stream=True, timeout=TIMEOUT,
    )
    r.raise_for_status()
    text = r.text
    chunks = parse_sse(text)
    content = ''.join(
        c['choices'][0]['delta'].get('content') or ''
        for c in chunks if c.get('choices')
    )
    tool_calls: list[dict] = []
    finish = None
    for c in chunks:
        ch = (c.get('choices') or [{}])[0]
        delta = ch.get('delta') or {}
        if delta.get('tool_calls'):
            tool_calls.extend(delta['tool_calls'])
        if ch.get('finish_reason'):
            finish = ch['finish_reason']
    has_tools_in_sse = 'tool_calls' in text
    ok = has_tools_in_sse and (bool(tool_calls) or finish == 'tool_calls')
    print('AGENT_TOOLS:', 'PASS' if ok else 'FAIL')
    print('  finish_reason:', finish)
    print('  tool_call_names:', [
        tc.get('function', {}).get('name') for tc in tool_calls
    ])
    print('  content_preview:', repr(content[:80]))
    print('  sse_has_tool_calls:', has_tools_in_sse)
    return ok


def test_copilot_debug_shows_agent_tools() -> bool:
    r = requests.get(f'{BASE}/copilot-debug', timeout=30)
    r.raise_for_status()
    body = r.json()
    entries: list[dict] = []
    for line in body.get('lines') or []:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    agent_entry = None
    for entry in reversed(entries):
        pipeline = entry.get('pipeline') or {}
        if pipeline.get('agent_tools') or entry.get('has_tools'):
            agent_entry = entry
            break
    ok = agent_entry is not None
    print('COPILOT_DEBUG:', 'PASS' if ok else 'FAIL')
    if agent_entry:
        print('  has_tools:', agent_entry.get('has_tools'))
        print('  agent_tools:', (agent_entry.get('pipeline') or {}).get('agent_tools'))
    return ok


def main() -> int:
    print(f'Testing proxy at {BASE} with model {MODEL}')
    results = [
        test_plain_chat(),
        test_agent_tools(),
        test_copilot_debug_shows_agent_tools(),
    ]
    passed = sum(results)
    print(f'Result: {passed}/{len(results)} passed')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
