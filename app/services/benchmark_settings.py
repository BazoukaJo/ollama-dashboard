"""Resolve benchmark inference options: dashboard-backed vs raw Ollama baseline."""
from __future__ import annotations

from typing import Any

from app.services.model_recommendation_profiles import match_recommendation_profile
from app.services.model_settings_helpers import (
    compute_fresh_recommended_settings_entry,
    get_default_settings_template,
)

# What most clients send when hitting :11434 directly without tuning.
BASELINE_BENCHMARK_OPTIONS: dict[str, Any] = {
    'num_predict': 256,
    'temperature': 0.2,
}

_THINKING_PROFILE_IDS = frozenset({
    'qwen3_thinking',
    'reasoning_thinking',
})


def model_uses_thinking(model_name: str) -> bool:
    """True when the model tends to spend tokens on internal reasoning."""
    profile = match_recommendation_profile({'name': model_name})
    if profile and str(profile.get('id') or '') in _THINKING_PROFILE_IDS:
        return True
    name = model_name.lower()
    return any(
        token in name
        for token in ('qwen3', 'deepseek-r1', 'lfm2', 'lfm2.5', 'nemotron', 'r1')
    )


def resolve_benchmark_timeout(model_name: str) -> int:
    """Scale HTTP timeout by model size (large models cold-start slower)."""
    name = model_name.lower()
    if any(tag in name for tag in ('coder-next', '80b', '70b', '72b', '671b')):
        return 600
    if any(tag in name for tag in ('35b', '33b', '32b', '30b', '27b')):
        return 300
    if any(tag in name for tag in ('12b', '14b', '13b', '11b')):
        return 180
    return 120


def resolve_dashboard_benchmark_options(service, model_name: str) -> dict[str, Any]:
    """Saved + fallback settings the dashboard proxy injects for this model."""
    options = dict(service.get_default_settings())
    entry = service.get_model_settings_with_fallback(model_name)
    if entry and isinstance(entry.get('settings'), dict):
        options.update(entry['settings'])
    return options


def resolve_profile_benchmark_options(service, model_name: str) -> dict[str, Any]:
    """Fresh profile-backed settings (recommended defaults for a new install)."""
    entry = compute_fresh_recommended_settings_entry(service, model_name)
    options = dict(get_default_settings_template())
    if isinstance(entry.get('settings'), dict):
        options.update(entry['settings'])
    return options


def resolve_baseline_benchmark_options(model_name: str) -> dict[str, Any]:
    """Minimal raw-Ollama defaults used as the comparison baseline."""
    return dict(BASELINE_BENCHMARK_OPTIONS)


def benchmark_options_summary(options: dict[str, Any]) -> dict[str, Any]:
    """Compact settings snapshot for API / report output."""
    keys = ('temperature', 'top_p', 'top_k', 'num_ctx', 'num_predict', 'repeat_penalty')
    return {k: options[k] for k in keys if k in options}
