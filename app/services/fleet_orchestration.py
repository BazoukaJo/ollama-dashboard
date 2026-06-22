"""Fleet routing and residency plans derived from benchmark results."""
from __future__ import annotations

from typing import Any


def build_fleet_routing_plan(
    advice: dict[str, Any],
    *,
    installed_models: list[str] | None = None,
) -> dict[str, Any]:
    """Pick fast / reasoning / coding models from benchmark rankings."""
    installed = {m.lower(): m for m in (installed_models or [])}
    rankings = (advice or {}).get('rankings') or {}
    by_cat = rankings.get('by_category') or {}
    overall = rankings.get('overall') or []
    speed = rankings.get('speed') or []

    def _pick(row: dict | None, fallback: str) -> str:
        if not row:
            return fallback
        name = str(row.get('model') or '').strip()
        return installed.get(name.lower(), name) or fallback

    fast_row = speed[0] if speed else (overall[0] if overall else None)
    reasoning_row = by_cat.get('reasoning') or by_cat.get('knowledge')
    coding_row = by_cat.get('coding') or {}

    fast = _pick(fast_row, 'gemma4:latest')
    reasoning = _pick(reasoning_row, 'qwen3.6:27B')
    coding = _pick(coding_row if isinstance(coding_row, dict) else None, 'Qwen3-Coder-Next:latest')

    # Prefer known coding tags when installed
    for candidate in (
        'qwen3-coder-next:latest', 'Qwen3-Coder-Next:latest',
        'qwen3-coder:30b', 'devstral:latest',
    ):
        key = candidate.lower()
        if key in installed:
            coding = installed[key]
            break

    for candidate in ('gemma4:latest', 'lfm2.5:latest'):
        if candidate.lower() in installed:
            fast = installed[candidate.lower()]
            break

    for candidate in ('qwen3.6:27b', 'qwen3.6:27B'):
        key = candidate.lower()
        if key in installed:
            reasoning = installed[key]
            break

    return {
        'routing_enabled': True,
        'routing_fast_model': fast,
        'routing_reasoning_model': reasoning,
        'routing_coding_model': coding,
        'source': 'benchmark_fleet',
    }


def build_residency_plan(
    routing: dict[str, Any],
    *,
    ram_gb: int = 64,
) -> dict[str, Any]:
    """64 GB dual-resident plan: fast pinned + heavy warm; coding on demand."""
    fast = routing.get('routing_fast_model') or 'gemma4:latest'
    heavy = routing.get('routing_reasoning_model') or 'qwen3.6:27B'
    coding = routing.get('routing_coding_model') or ''
    return {
        'RESIDENCY_FAST_MODEL': fast,
        'RESIDENCY_HEAVY_MODEL': heavy,
        'RESIDENCY_KEEP_ALIVE': -1,
        'RESIDENCY_HEAVY_KEEP_ALIVE': '30m',
        'RESIDENCY_CODING_MODEL': coding,
        'notes': (
            f'{ram_gb}GB: pin {fast} + warm {heavy}; load {coding or "coder"} on coding sessions only.'
        ),
    }


def apply_routing_to_default_model(service, plan: dict[str, Any], default_model: str | None = None) -> bool:
    """Save three-tier routing on the fleet default model (usually fast tier)."""
    target = (default_model or plan.get('routing_fast_model') or 'gemma4:latest').strip()
    if not target:
        return False
    entry = service.get_model_settings_with_fallback(target) or {}
    settings = dict(entry.get('settings') or {})
    client = dict(entry.get('client') or entry.get('copilot') or {})
    for key in (
        'routing_enabled', 'routing_fast_model',
        'routing_reasoning_model', 'routing_coding_model',
    ):
        if key in plan:
            client[key] = plan[key]
    return service.save_model_settings(
        target,
        settings,
        source='fleet_orchestration',
        copilot=client,
    )
