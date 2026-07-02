"""Parse API proxy logs for status and analytics."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Models used only by pytest / smoke scripts — not real Ollama models.
_SYNTHETIC_MODEL_NAMES = frozenset({
    'test-model', 'copilot-test', 'qwen-test', 'missing',
})
_SYNTHETIC_MODEL_PATTERN = re.compile(
    r'^(test-|pytest-|mock-)|(-test|_test)$',
    re.I,
)


def _is_synthetic_model(name: str | None) -> bool:
    if not name or not str(name).strip():
        return True
    s = str(name).strip()
    if s in _SYNTHETIC_MODEL_NAMES:
        return True
    return bool(_SYNTHETIC_MODEL_PATTERN.search(s.split(':', maxsplit=1)[0]))


def _last_real_chat_record(chat_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for rec in reversed(chat_records):
        model = rec.get('model_resolved') or rec.get('model_in')
        if not _is_synthetic_model(model):
            return rec
    return None


def _parse_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return None
    return rec if isinstance(rec, dict) else None


def read_log_records(data_dir: str | Path, *, limit: int = 500) -> list[dict[str, Any]]:
    log_file = Path(data_dir) / 'copilot_proxy.log'
    if not log_file.is_file():
        return []
    try:
        lines = log_file.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        rec = _parse_line(line)
        if rec:
            records.append(rec)
    return records


def client_proxy_status(data_dir: str | Path, *, ollama_base_url: str | None = None) -> dict[str, Any]:
    """Summarize external client / API proxy activity for the dashboard UI."""
    from app.services import copilot_proxy

    records = read_log_records(data_dir)
    chat_records = [r for r in records if r.get('model_in') or r.get('model_resolved')]
    hits = [r for r in records if r.get('kind') == 'hit']

    last_chat = _last_real_chat_record(chat_records)
    last_hit = hits[-1] if hits else None
    last_any = records[-1] if records else None

    model_counts: Counter[str] = Counter()
    trim_count = 0
    for rec in chat_records:
        model = rec.get('model_resolved') or rec.get('model_in') or ''
        if model and not _is_synthetic_model(str(model)):
            model_counts[str(model)] += 1
        if rec.get('context_trimmed'):
            trim_count += 1

    running_models: list[str] = []
    if ollama_base_url:
        running_models = copilot_proxy.list_running_model_names(ollama_base_url)

    allocated_ctx = None
    loaded_model = None
    if last_chat and ollama_base_url and running_models:
        loaded_model = last_chat.get('model_resolved') or last_chat.get('model_in')
        if loaded_model and str(loaded_model) in running_models:
            allocated_ctx = copilot_proxy.loaded_context_length(ollama_base_url, str(loaded_model))
        elif running_models:
            loaded_model = running_models[0]
            allocated_ctx = copilot_proxy.loaded_context_length(ollama_base_url, str(loaded_model))

    saved_ctx = None
    if last_chat:
        saved_ctx = (last_chat.get('options_num_ctx')
                     or (last_chat.get('pipeline') or {}).get('num_ctx'))

    ctx_mismatch = (
        allocated_ctx is not None
        and saved_ctx is not None
        and int(allocated_ctx) != int(saved_ctx)
    )

    last_model_logged = (last_chat or {}).get('model_resolved') or (last_chat or {}).get('model_in')
    display_model = loaded_model if running_models else None

    return {
        'proxy_active': bool(last_hit or last_chat),
        'model_loaded': bool(running_models),
        'running_models': running_models,
        'last_request_at': (last_any or {}).get('ts'),
        'last_chat_at': (last_chat or {}).get('ts'),
        'last_model': display_model,
        'last_model_logged': last_model_logged,
        'last_path': (last_hit or last_chat or {}).get('path'),
        'requests_logged': len(records),
        'chat_requests': len(chat_records),
        'proxy_hits': len(hits),
        'context_trim_events': trim_count,
        'top_models': [{'model': m, 'count': c} for m, c in model_counts.most_common(5)],
        'allocated_ctx': allocated_ctx,
        'saved_ctx': saved_ctx,
        'ctx_mismatch': ctx_mismatch,
        'loaded_model': loaded_model,
        **_residency_summary(ollama_base_url),
    }


def _residency_summary(ollama_base_url: str | None) -> dict[str, Any]:
    if not ollama_base_url:
        return {}
    try:
        from app.services.model_residency import get_residency_status

        status = get_residency_status(ollama_base_url)
        return {
            'resident_fast_model': status.get('resident_fast_model'),
            'resident_fast_loaded': status.get('resident_fast_loaded'),
            'resident_heavy_model': status.get('resident_heavy_model'),
            'resident_heavy_loaded': status.get('resident_heavy_loaded'),
            'pinned_models': [p.get('model') for p in status.get('pinned') or []],
        }
    except Exception:  # noqa: BLE001 - status panel must stay up
        return {}


def client_proxy_analytics(data_dir: str | Path) -> dict[str, Any]:
    """Aggregate stats for analytics panel."""
    records = read_log_records(data_dir, limit=2000)
    chat = [r for r in records if r.get('model_in') or r.get('model_resolved')]
    errors = [r for r in records if r.get('kind') == 'error']
    trimmed = sum(1 for r in chat if r.get('context_trimmed'))

    by_day: Counter[str] = Counter()
    for rec in chat:
        ts = rec.get('ts') or ''
        day = ts[:10] if len(ts) >= 10 else 'unknown'
        by_day[day] += 1

    return {
        'total_logged': len(records),
        'chat_requests': len(chat),
        'errors': len(errors),
        'trimmed_requests': trimmed,
        'requests_by_day': dict(by_day),
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }


# Legacy aliases
copilot_status = client_proxy_status
copilot_analytics = client_proxy_analytics


def diagnose_recent_activity(data_dir: str | Path, *, limit: int = 300) -> dict[str, Any]:
    """Classify the most recent external-client (VS Code/Cursor/etc.) proxy activity into a
    plain-language diagnosis: connection error, timeout, context truncation, agent tool-turn
    degeneracy, output cap, empty reply, or a normal completion.

    Built entirely on the existing structured ``copilot_proxy.log`` records (``kind``:
    hit/chat/response) already written by ``log_copilot_request``/``log_copilot_response`` —
    this is a read-only classifier, not a new logging system.
    """
    records = read_log_records(data_dir, limit=limit)
    chats = [r for r in records if r.get('kind') == 'chat']
    responses = [r for r in records if r.get('kind') == 'response']

    if not chats and not responses:
        return {
            'category': 'no_activity',
            'message': 'No external client (VS Code, Cursor, etc.) requests logged yet.',
            'detail': {},
        }

    # Pair each response with the chat request that most recently preceded it in log order,
    # so the diagnosis reflects the actual last turn rather than an unrelated earlier one.
    last_chat: dict[str, Any] | None = None
    last_pair: tuple[dict[str, Any] | None, dict[str, Any]] | None = None
    for rec in records:
        if rec.get('kind') == 'chat':
            last_chat = rec
        elif rec.get('kind') == 'response':
            last_pair = (last_chat, rec)

    if last_pair is None:
        model_name = (chats[-1] if chats else {}).get('model_resolved') or (chats[-1] if chats else {}).get('model_in')
        return {
            'category': 'request_only',
            'message': (
                f'A request for {model_name or "a model"} was logged, but no response summary '
                'was recorded yet (still in flight, or the dashboard was restarted mid-request).'
            ),
            'detail': {'model': model_name},
        }

    chat_rec, response_rec = last_pair
    trim_meta = ((chat_rec or {}).get('pipeline') or {}).get('context_trim') or {}
    model_name = (
        (chat_rec or {}).get('model_resolved') or (chat_rec or {}).get('model_in')
        or response_rec.get('model')
    )

    error = response_rec.get('error')
    content_chars = response_rec.get('content_chars', 0)
    tool_calls = response_rec.get('tool_calls', 0)
    agent = response_rec.get('agent')
    finish_reason = response_rec.get('finish_reason')

    if error and 'upstream_status_504' in str(error):
        category = 'first_token_timeout'
        message = (
            f'The last request to {model_name or "the model"} timed out waiting for the first '
            'token — the model is likely still loading or too large/slow for available VRAM. '
            'Try pre-loading the model with Start, or use a smaller/faster model.'
        )
    elif error and any(word in str(error).lower() for word in ('connection', 'refused', 'unreachable')):
        category = 'connection_error'
        message = (
            'Could not reach Ollama for the last request. Check that the Ollama service is '
            'running and that OLLAMA_HOST/OLLAMA_PORT are correct.'
        )
    elif error:
        category = 'upstream_error'
        message = f'The last request to {model_name or "the model"} failed mid-stream: {error}.'
    elif content_chars == 0 and tool_calls == 0:
        category = 'empty_reply'
        message = (
            f'The last response from {model_name or "the model"} was empty (no text, no tool '
            'call). The proxy relayed exactly what Ollama produced — check the model is '
            'healthy and try again.'
        )
    elif agent and content_chars <= 1 and tool_calls == 0:
        category = 'agent_degeneracy'
        message = (
            f'{model_name or "The model"} returned only a token or two on an Agent/tool-result '
            'turn. This is a known behavior of large, CPU-offloaded reasoning models on agent '
            'turns — try Ask mode instead, or a model that fits fully in VRAM.'
        )
    elif trim_meta.get('trimmed'):
        category = 'context_trimmed'
        before = trim_meta.get('tokens_before')
        after = trim_meta.get('tokens_after')
        message = (
            f'Your last prompt to {model_name or "the model"} was trimmed to fit its context '
            f'window (roughly {before} → {after} estimated tokens), which may have removed '
            'earlier instructions or history. Increase Context (num_ctx) in Settings if this '
            'is unexpected.'
        )
    elif finish_reason == 'length':
        category = 'output_capped'
        message = (
            f'The last response from {model_name or "the model"} was cut off at the output '
            'token limit (num_predict). Increase it in Settings if you need longer replies.'
        )
    else:
        category = 'ok'
        message = f'The last request to {model_name or "the model"} completed normally.'

    return {
        'category': category,
        'message': message,
        'detail': {
            'model': model_name,
            'error': error,
            'content_chars': content_chars,
            'tool_calls': tool_calls,
            'agent': agent,
            'finish_reason': finish_reason,
            'context_trim': trim_meta,
            'ts': response_rec.get('ts'),
        },
    }
