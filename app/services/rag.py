"""Minimal local RAG: sqlite-backed chunk store and retrieval (optional, env-gated)."""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_db_path: Path | None = None

_CHUNK_SIZE = 1200


def _database_path() -> Path:
    global _db_path
    if _db_path is None:
        base = Path(os.getenv('OLLAMA_DASHBOARD_DATA') or os.getenv('DATA_DIR') or 'data')
        base.mkdir(parents=True, exist_ok=True)
        _db_path = base / 'rag_index.sqlite'
    return _db_path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_database_path()), check_same_thread=False)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS chunks ('
        'id INTEGER PRIMARY KEY, path TEXT, chunk_index INTEGER, content TEXT)'
    )
    conn.execute('CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)')
    return conn


def index_file(path: Path, content: str) -> int:
    """Index a single file into chunks; returns chunk count."""
    rel = str(path)
    chunks: list[str] = []
    text = content or ''
    for i in range(0, len(text), _CHUNK_SIZE):
        piece = text[i:i + _CHUNK_SIZE].strip()
        if piece:
            chunks.append(piece)
    with _lock:
        conn = _connect()
        conn.execute('DELETE FROM chunks WHERE path = ?', (rel,))
        for idx, piece in enumerate(chunks):
            conn.execute(
                'INSERT INTO chunks(path, chunk_index, content) VALUES (?, ?, ?)',
                (rel, idx, piece),
            )
        conn.commit()
        conn.close()
    return len(chunks)


def index_workspace(root: Path, *, max_files: int = 500) -> dict[str, Any]:
    """Walk workspace and index text-like files (respects .gitignore basics)."""
    ignore_dirs = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build'}
    ignore_ext = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.zip', '.exe', '.dll', '.so'}
    indexed = 0
    skipped = 0
    for path in root.rglob('*'):
        if indexed >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in ignore_dirs for part in path.parts):
            continue
        if path.suffix.lower() in ignore_ext:
            skipped += 1
            continue
        try:
            if path.stat().st_size > 512_000:
                skipped += 1
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            skipped += 1
            continue
        if not text.strip():
            continue
        index_file(path.relative_to(root), text)
        indexed += 1
    return {'indexed_files': indexed, 'skipped': skipped, 'root': str(root.resolve())}


def _score_chunk(query: str, content: str) -> int:
    q = query.lower()
    c = content.lower()
    score = 0
    for token in q.split():
        if len(token) > 2 and token in c:
            score += 1
    return score


def retrieve(query: str, *, top_k: int = 5) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    with _lock:
        conn = _connect()
        rows = conn.execute('SELECT path, chunk_index, content FROM chunks').fetchall()
        conn.close()
    scored = []
    for path, idx, content in rows:
        s = _score_chunk(query, content)
        if s > 0:
            scored.append({'path': path, 'chunk_index': idx, 'content': content, 'score': s})
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:top_k]


def rag_status() -> dict[str, Any]:
    with _lock:
        conn = _connect()
        count = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        files = conn.execute('SELECT COUNT(DISTINCT path) FROM chunks').fetchone()[0]
        conn.close()
    return {
        'enabled': os.getenv('RAG_ENABLED', '').strip().lower() in ('1', 'true', 'yes'),
        'chunks': count,
        'files': files,
        'db_path': str(_database_path()),
    }


def inject_rag_context(messages: list[Any]) -> tuple[list[Any], dict[str, Any]]:
    """Append top retrieved chunks to the last user message."""
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    if not msgs:
        return msgs, {'injected': False}
    last = msgs[-1]
    if last.get('role') != 'user':
        return msgs, {'injected': False}
    query = last.get('content')
    if not isinstance(query, str) or not query.strip():
        return msgs, {'injected': False}
    hits = retrieve(query, top_k=int(os.getenv('RAG_TOP_K', '5')))
    if not hits:
        return msgs, {'injected': False, 'hits': 0}
    block = '\n\n'.join(
        f'[{h["path"]}]\n{h["content"][:800]}' for h in hits
    )
    updated = dict(last)
    updated['content'] = f'{query}\n\n--- Relevant codebase context ---\n{block}'
    return [*msgs[:-1], updated], {'injected': True, 'hits': len(hits)}
