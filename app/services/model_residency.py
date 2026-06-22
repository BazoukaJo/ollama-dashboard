"""Multi-model RAM residency: pin a fast tier + optional heavy tier in Ollama memory.

Requires Ollama server env (set on the Ollama process, not only dashboard .env):
  OLLAMA_MAX_LOADED_MODELS=2
  OLLAMA_KEEP_ALIVE=-1
  OLLAMA_NUM_PARALLEL=1

See docs/GUIDE.md — Multi-model residency.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.services.service_errors import HTTP_SERVICE_ERRORS

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pinned: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class PinSpec:
    model: str
    role: str
    keep_alive: str | int


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name, 'true' if default else 'false').strip().lower()
    return raw in ('1', 'true', 'yes', 'on')


def _parse_keep_alive(raw: str | None) -> str | int:
    if raw is None or not str(raw).strip():
        return -1
    text = str(raw).strip()
    if text in ('-1', 'inf', 'infinite'):
        return -1
    return text


def parse_residency_env() -> list[PinSpec]:
    """Read RESIDENCY_FAST_MODEL / RESIDENCY_HEAVY_MODEL from environment."""
    specs: list[PinSpec] = []
    keep = _parse_keep_alive(os.getenv('RESIDENCY_KEEP_ALIVE', '-1'))
    fast = os.getenv('RESIDENCY_FAST_MODEL', '').strip()
    if not fast:
        fast = os.getenv('COPILOT_PREWARM_MODEL', '').strip()
    heavy = os.getenv('RESIDENCY_HEAVY_MODEL', '').strip()
    if fast:
        specs.append(PinSpec(model=fast, role='fast', keep_alive=keep))
    if heavy and heavy != fast:
        heavy_keep = os.getenv('RESIDENCY_HEAVY_KEEP_ALIVE', '30m').strip() or '30m'
        specs.append(PinSpec(model=heavy, role='heavy', keep_alive=_parse_keep_alive(heavy_keep)))
    return specs


def register_pin(model_name: str, *, role: str = 'custom', keep_alive: str | int = -1) -> None:
    if not model_name:
        return
    with _lock:
        _pinned[model_name] = {
            'role': role,
            'keep_alive': keep_alive,
            'pinned_at': time.time(),
        }


def unpin_model(model_name: str) -> bool:
    """Remove model from pin registry. Returns True if it was pinned."""
    if not model_name:
        return False
    with _lock:
        return _pinned.pop(model_name, None) is not None


def is_pinned(model_name: str) -> bool:
    if not model_name:
        return False
    with _lock:
        return model_name in _pinned


def pin_keep_alive_for(model_name: str) -> str | int | None:
    """Return keep_alive for a pinned model, else None (use default copilot keep-alive)."""
    if not model_name:
        return None
    with _lock:
        entry = _pinned.get(model_name)
    if not entry:
        return None
    return entry.get('keep_alive', -1)


def list_pinned() -> list[dict[str, Any]]:
    with _lock:
        return [
            {'model': name, **meta}
            for name, meta in sorted(_pinned.items())
        ]


def fetch_ps_models(ollama_base_url: str) -> list[dict[str, Any]]:
    try:
        response = requests.get(f'{ollama_base_url.rstrip("/")}/api/ps', timeout=10)
        if response.status_code != 200:
            return []
        data = response.json()
        return data.get('models') or [] if isinstance(data, dict) else []
    except HTTP_SERVICE_ERRORS as err:
        logger.debug('fetch_ps_models failed: %s', err)
        return []


def recommend_ollama_server_env(*, system_ram_gb: int = 64) -> dict[str, Any]:
    """Suggested Ollama *server* environment (user must set on Ollama process)."""
    return {
        'OLLAMA_MAX_LOADED_MODELS': '2',
        'OLLAMA_KEEP_ALIVE': '-1',
        'OLLAMA_NUM_PARALLEL': '1',
        'notes': (
            f'With ~{system_ram_gb}GB RAM: pin fast 8B + one heavy model; '
            'lower heavy num_ctx before raising OLLAMA_NUM_PARALLEL.'
        ),
    }


def pin_model_sync(
    svc,
    ollama_base_url: str,
    model_name: str,
    *,
    role: str = 'custom',
    keep_alive: str | int = -1,
    prompt: str = 'ready',
) -> dict[str, Any]:
    """Load model into memory with keep_alive (sync)."""
    from app.services.warm_start import build_warm_start_payload

    if not model_name:
        return {'success': False, 'error': 'model name required'}

    generate_url = f'{ollama_base_url.rstrip("/")}/api/generate'
    payload = build_warm_start_payload(svc, model_name, prompt=prompt, keep_alive=str(keep_alive))
    payload['keep_alive'] = keep_alive

    try:
        response = svc._session.post(generate_url, json=payload, timeout=300)
        if response.status_code != 200:
            return {
                'success': False,
                'error': f'HTTP {response.status_code}: {response.text[:200]}',
            }
        try:
            body = response.json()
            if isinstance(body, dict) and body.get('error'):
                return {'success': False, 'error': str(body['error'])}
        except ValueError:
            pass
        register_pin(model_name, role=role, keep_alive=keep_alive)
        return {
            'success': True,
            'model': model_name,
            'role': role,
            'keep_alive': keep_alive,
        }
    except HTTP_SERVICE_ERRORS as exc:
        return {'success': False, 'error': str(exc)}


def schedule_pin(
    executor,
    svc,
    ollama_base_url: str,
    spec: PinSpec,
) -> None:
    """Background pin (startup)."""

    def _run() -> None:
        result = pin_model_sync(
            svc, ollama_base_url, spec.model,
            role=spec.role, keep_alive=spec.keep_alive,
        )
        if result.get('success'):
            logger.info('Pinned resident model %s (%s) keep_alive=%s', spec.model, spec.role, spec.keep_alive)
        else:
            logger.warning('Resident pin failed for %s: %s', spec.model, result.get('error'))

    executor.submit(_run)


def get_residency_status(ollama_base_url: str) -> dict[str, Any]:
    """Merge pin registry with live Ollama /api/ps."""
    ps = fetch_ps_models(ollama_base_url)
    loaded_names = {str(m.get('name') or '') for m in ps if m.get('name')}
    pinned = list_pinned()
    comparisons = []
    for entry in pinned:
        name = entry['model']
        loaded = name in loaded_names
        ps_row = next((m for m in ps if m.get('name') == name), {})
        comparisons.append({
            'model': name,
            'role': entry.get('role'),
            'keep_alive': entry.get('keep_alive'),
            'loaded': loaded,
            'size_vram': ps_row.get('size_vram'),
            'expires_at': ps_row.get('expires_at'),
        })
    fast = next((c for c in comparisons if c.get('role') == 'fast'), None)
    heavy = next((c for c in comparisons if c.get('role') == 'heavy'), None)
    return {
        'pinned': comparisons,
        'loaded_models': sorted(loaded_names),
        'resident_fast_model': fast.get('model') if fast else None,
        'resident_fast_loaded': bool(fast and fast.get('loaded')),
        'resident_heavy_model': heavy.get('model') if heavy else None,
        'resident_heavy_loaded': bool(heavy and heavy.get('loaded')),
        'ollama_server_env': recommend_ollama_server_env(),
        'configured': [
            {'model': s.model, 'role': s.role, 'keep_alive': s.keep_alive}
            for s in parse_residency_env()
        ],
    }


def startup_residency_from_env(app, ollama_service) -> None:
    """Pin fast + heavy models on dashboard startup (background, best-effort)."""
    if not _env_bool('RESIDENCY_ON_START', True):
        return
    specs = parse_residency_env()
    if not specs:
        return
    import concurrent.futures

    host, port = ollama_service._get_ollama_host_port()
    base = f'http://{host}:{int(port)}'
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix='model-residency',
    )

    def _sequential_pins() -> None:
        for spec in specs:
            pin_model_sync(
                ollama_service, base, spec.model,
                role=spec.role, keep_alive=spec.keep_alive,
            )

    executor.submit(_sequential_pins)
    logger.info(
        'Scheduled residency pins for: %s',
        ', '.join(f'{s.role}={s.model}' for s in specs),
    )
