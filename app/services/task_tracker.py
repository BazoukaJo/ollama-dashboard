"""In-process tracker for long-running dashboard tasks (benchmarks, tune loops).

Provides status for operations that may take minutes so clients never wait blind.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

_lock = threading.Lock()
_tasks: dict[str, dict[str, Any]] = {}
_MAX_TASKS = 50


def _prune_old() -> None:
    if len(_tasks) <= _MAX_TASKS:
        return
    finished = [
        (tid, t.get('updated_at') or 0)
        for tid, t in _tasks.items()
        if t.get('state') in ('done', 'error', 'cancelled')
    ]
    finished.sort(key=lambda x: x[1])
    for tid, _ in finished[: max(0, len(_tasks) - _MAX_TASKS)]:
        _tasks.pop(tid, None)


def create_task(
    kind: str,
    *,
    label: str = '',
    total_steps: int = 1,
    meta: dict[str, Any] | None = None,
) -> str:
    task_id = uuid.uuid4().hex[:12]
    now = time.time()
    with _lock:
        _tasks[task_id] = {
            'id': task_id,
            'kind': kind,
            'label': label or kind,
            'state': 'running',
            'step': 0,
            'total_steps': max(1, int(total_steps)),
            'percent': 0,
            'message': 'Starting…',
            'created_at': now,
            'updated_at': now,
            'meta': dict(meta or {}),
            'result': None,
            'error': None,
        }
        _prune_old()
    return task_id


def update_task(
    task_id: str,
    *,
    step: int | None = None,
    message: str | None = None,
    percent: int | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task or task.get('state') != 'running':
            return
        if step is not None:
            task['step'] = int(step)
            if percent is None and task['total_steps']:
                task['percent'] = min(99, int(100 * task['step'] / task['total_steps']))
        if message is not None:
            task['message'] = message
        if percent is not None:
            task['percent'] = min(99, max(0, int(percent)))
        if meta:
            task['meta'].update(meta)
        task['updated_at'] = time.time()


def complete_task(task_id: str, result: Any = None) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task['state'] = 'done'
        task['percent'] = 100
        task['message'] = 'Complete'
        task['result'] = result
        task['updated_at'] = time.time()


def fail_task(task_id: str, error: str) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task['state'] = 'error'
        task['message'] = error[:500]
        task['error'] = error
        task['updated_at'] = time.time()


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        task = _tasks.get(task_id)
        return dict(task) if task else None


def list_tasks(*, limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        rows = sorted(_tasks.values(), key=lambda t: t.get('updated_at', 0), reverse=True)
        return [dict(r) for r in rows[:limit]]
