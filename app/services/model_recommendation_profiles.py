"""Benchmark-backed recommendation profiles for per-model default settings."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

_CONTEXT_KEYS = frozenset({
    'context_target', 'context_min', 'context_fraction', 'context_max',
})
_SETTING_KEYS = frozenset({
    'temperature', 'top_k', 'top_p', 'num_ctx', 'seed', 'num_predict',
    'repeat_last_n', 'repeat_penalty', 'presence_penalty', 'frequency_penalty',
    'stop', 'min_p', 'typical_p', 'penalize_newline', 'mirostat', 'mirostat_tau',
    'mirostat_eta',
})


@lru_cache(maxsize=1)
def _load_profiles_data() -> dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), 'model_recommendation_profiles.json')
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _name_matches_pattern(name_l: str, pattern: str) -> bool:
    pat = pattern.strip().lower()
    if not pat:
        return False
    if pat.endswith(':'):
        return name_l.startswith(pat) or (':' in name_l and name_l.split(':', 1)[0] + ':' == pat)
    return pat in name_l


def match_recommendation_profile(model_info: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the first matching profile dict, or None."""
    info = model_info or {}
    name_l = str(info.get('name') or '').lower()
    if not name_l:
        return None
    for profile in _load_profiles_data().get('profiles') or []:
        if not isinstance(profile, dict):
            continue
        patterns = profile.get('patterns') or []
        excludes = profile.get('exclude_patterns') or []
        if not any(_name_matches_pattern(name_l, p) for p in patterns):
            continue
        if any(_name_matches_pattern(name_l, p) for p in excludes):
            continue
        return profile
    return None


def apply_profile_settings(
    settings: dict[str, Any],
    profile: dict[str, Any] | None,
    *,
    max_ctx: int | None,
    ctx_cap: int,
) -> dict[str, Any]:
    """Merge profile sampling settings and resolve context targets."""
    if not profile:
        return settings
    raw = profile.get('settings') if isinstance(profile.get('settings'), dict) else {}
    for key, value in raw.items():
        if key in _CONTEXT_KEYS:
            continue
        if key in _SETTING_KEYS:
            settings[key] = value

    target = raw.get('context_target')
    ctx_min = raw.get('context_min', 4096)
    fraction = raw.get('context_fraction')
    if isinstance(target, (int, float)):
        settings['num_ctx'] = max(int(settings.get('num_ctx', 8192)), int(target))
    if max_ctx and fraction:
        try:
            frac_target = int(max_ctx * float(fraction))
            settings['num_ctx'] = max(settings.get('num_ctx', 8192), frac_target)
        except (TypeError, ValueError):
            pass
    if ctx_min:
        settings['num_ctx'] = max(settings.get('num_ctx', 8192), int(ctx_min))

    settings['num_ctx'] = min(settings.get('num_ctx', 8192), ctx_cap)
    if max_ctx is not None:
        settings['num_ctx'] = min(settings['num_ctx'], max_ctx)
    return settings


def resolve_num_ctx_for_model(
    settings: dict[str, Any],
    *,
    max_ctx: int | None,
    ctx_cap: int,
    param_size: float | None = None,
) -> int:
    """Final num_ctx pass: respect model window, rig cap, and parameter-class floor."""
    floor = 4096
    if param_size is not None:
        if param_size <= 2:
            floor = 4096
        elif param_size <= 8:
            floor = 8192
        elif param_size <= 14:
            floor = 8192
        else:
            floor = 12288

    num_ctx = max(int(settings.get('num_ctx', 8192)), floor)
    num_ctx = min(num_ctx, ctx_cap)
    if max_ctx is not None:
        # Use up to 50% of native window on strong rigs, capped by ctx_cap.
        soft_target = min(max_ctx, max(num_ctx, int(max_ctx * 0.5)))
        num_ctx = min(soft_target, ctx_cap)
        num_ctx = min(num_ctx, max_ctx)
    return num_ctx
