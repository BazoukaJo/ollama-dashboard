"""Turn benchmark results into validated settings and agentic tuning advice."""
from __future__ import annotations

from typing import Any

from app.services.benchmark_settings import (
    benchmark_options_summary,
    model_uses_thinking,
)
from app.services.copilot_extras import DEFAULT_CLIENT_EXTRAS, get_client_extras
from app.services.model_recommendation_profiles import match_recommendation_profile

_AGENT_NUM_PREDICT_FLOOR = 4096
_AGENT_NUM_CTX_FLOOR = 8192
_LONG_SESSION_NUM_CTX = 16384


def _profile_settings(model_name: str) -> dict[str, Any]:
    profile = match_recommendation_profile({'name': model_name})
    if not profile:
        return {}
    raw = profile.get('settings')
    return dict(raw) if isinstance(raw, dict) else {}


def _case_notes(cases: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for case in cases or []:
        for note in case.get('notes') or []:
            notes.append(str(note))
    return notes


def _has_truncation(cases: list[dict[str, Any]]) -> bool:
    return any('truncated' in note.lower() for note in _case_notes(cases))


def _timeout_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for case in cases or []:
        if case.get('status') != 'error':
            continue
        err = str(case.get('error') or '').lower()
        if 'timed out' in err or 'timeout' in err:
            out.append(case)
    return out


def _failed_categories(cases: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_cat: dict[str, list[str]] = {}
    for case in cases or []:
        if case.get('status') != 'success' or case.get('passed'):
            continue
        cat = str(case.get('category') or 'general')
        by_cat.setdefault(cat, []).append(str(case.get('id') or ''))
    return by_cat


def _settings_drift(current: dict[str, Any], profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    keys = ('temperature', 'top_p', 'top_k', 'num_ctx', 'num_predict', 'repeat_penalty')
    drift: dict[str, dict[str, Any]] = {}
    for key in keys:
        if key not in current and key not in profile:
            continue
        cur = current.get(key)
        prof = profile.get(key)
        if prof is None:
            continue
        if cur != prof:
            drift[key] = {'current': cur, 'profile': prof}
    return drift


def _validation_status(
    benchmark: dict[str, Any],
    *,
    suggested_settings: dict[str, Any],
    suggested_client: dict[str, Any],
) -> str:
    if benchmark.get('error_count', 0) > 0:
        return 'critical'
    if suggested_settings or suggested_client:
        return 'needs_tuning'
    if float(benchmark.get('overall_score', 0)) < 70:
        return 'needs_tuning'
    if int(benchmark.get('passed_count', 0)) < int(benchmark.get('total_count', 8)):
        return 'needs_tuning'
    return 'ok'


def _build_agentic_recommendations(
    model_name: str,
    *,
    current_settings: dict[str, Any],
    profile_settings: dict[str, Any],
    client_extras: dict[str, Any],
    model_info: dict[str, Any] | None,
    benchmark: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    info = model_info if isinstance(model_info, dict) else {}
    has_tools = info.get('has_tools') is True
    has_reasoning = info.get('has_reasoning') is True or model_uses_thinking(model_name)
    thinking = model_uses_thinking(model_name)

    ctx_target = profile_settings.get('context_target') or _AGENT_NUM_CTX_FLOOR
    try:
        ctx_target = int(ctx_target)
    except (TypeError, ValueError):
        ctx_target = _AGENT_NUM_CTX_FLOOR

    num_ctx = int(current_settings.get('num_ctx') or _AGENT_NUM_CTX_FLOOR)
    agent_ctx = max(num_ctx, ctx_target, _LONG_SESSION_NUM_CTX if has_tools else _AGENT_NUM_CTX_FLOOR)

    num_predict = int(current_settings.get('num_predict') or 512)
    profile_np = int(profile_settings.get('num_predict') or _AGENT_NUM_PREDICT_FLOOR)
    agent_np = max(num_predict, profile_np, _AGENT_NUM_PREDICT_FLOOR if has_tools or thinking else 2048)

    roles: list[str] = []
    if has_tools:
        roles.extend(['ask_agent', 'mcp_tools', 'copilot_tool_calls'])
    elif thinking:
        roles.append('deep_reasoning_chat')
    else:
        roles.append('fast_chat')

    communication: list[str] = [
        'Route multi-turn work through http://127.0.0.1:5000/ollama (proxy injects num_ctx and sampling).',
        'Keep context_trim_enabled so long agent transcripts are trimmed instead of hard-failing.',
    ]
    if has_tools:
        communication.extend([
            'Use /ollama/v1/chat/completions with tool messages for agent loops (not one-shot /api/generate).',
            'Raise ASK_AGENT_MAX_ITERATIONS (default 8) for multi-step tool chains.',
        ])
    if thinking:
        communication.extend([
            'For IDE short Q&A set client copilot_think=off; enable think for long reasoning sessions only.',
            'Benchmark uses think:false for scoring — agent mode can enable thinking when depth matters.',
        ])
    if baseline is not None:
        lift = float(benchmark.get('overall_score', 0)) - float(baseline.get('overall_score', 0))
        if lift >= 25:
            communication.append(
                f'Never point clients at raw :11434 for this model (benchmark lift +{lift:.0f} via dashboard).'
            )

    if float(benchmark.get('avg_response_time', 0)) > 30:
        communication.append(
            'Enable COPILOT_PREWARM_MODEL and keep_alive so long sessions avoid cold reload between turns.'
        )

    return {
        'recommended_roles': roles,
        'settings': {
            'num_ctx': agent_ctx,
            'num_predict': agent_np,
        },
        'client': {
            'context_trim_enabled': True,
            'copilot_think': 'on' if has_reasoning and has_tools else (
                'off' if thinking else str(client_extras.get('copilot_think') or 'off')
            ),
        },
        'proxy': {
            'url': 'http://127.0.0.1:5000/ollama',
            'keep_alive_minutes': 15,
            'prewarm_recommended': float(benchmark.get('avg_response_time', 0)) > 15,
        },
        'env': {
            'ASK_AGENT_MAX_ITERATIONS': 12 if has_tools else 8,
            'CONTEXT_TRIM_ENABLED': True,
            'COPILOT_KEEP_ALIVE': True,
        },
        'communication': communication,
        'session_notes': (
            'For hour-long agent work: stable num_ctx, trim old tool output, keep model loaded, '
            'use chat (not generate) so message history is preserved across turns.'
        ),
    }


def analyze_benchmark_improvements(
    model_name: str,
    benchmark: dict[str, Any],
    *,
    current_settings: dict[str, Any],
    settings_source: str = 'unknown',
    client_extras: dict[str, Any] | None = None,
    profile_settings: dict[str, Any] | None = None,
    model_info: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate current settings and suggest tuning from benchmark signals."""
    profile = dict(profile_settings or _profile_settings(model_name))
    current = dict(current_settings or {})
    client = dict(client_extras or DEFAULT_CLIENT_EXTRAS)
    cases = benchmark.get('cases') or []

    suggested_settings: dict[str, Any] = {}
    suggested_client: dict[str, Any] = {}
    changes: list[str] = []
    gaps: list[str] = []

    drift = _settings_drift(current, profile)
    for key, pair in drift.items():
        if key in ('num_ctx', 'num_predict'):
            try:
                cur_v = float(pair['current'] or 0)
                prof_v = float(pair['profile'] or 0)
            except (TypeError, ValueError):
                continue
            if key == 'num_ctx' and cur_v < prof_v * 0.75:
                suggested_settings[key] = int(prof_v)
                changes.append(
                    f'num_ctx {int(cur_v)} is below profile target {int(prof_v)} — '
                    'long chats will lose context early'
                )
            if key == 'num_predict' and cur_v < prof_v * 0.5:
                suggested_settings[key] = int(prof_v)
                changes.append(
                    f'num_predict {int(cur_v)} is low vs profile {int(prof_v)} — '
                    'answers may cut off mid-task'
                )
        elif key in ('temperature', 'top_p', 'top_k', 'repeat_penalty'):
            suggested_settings[key] = pair['profile']
            changes.append(
                f'{key} drifts from profile ({pair["current"]} vs recommended {pair["profile"]})'
            )

    if _has_truncation(cases):
        cur_np = int(current.get('num_predict') or 256)
        profile_np = int(profile.get('num_predict') or _AGENT_NUM_PREDICT_FLOOR)
        target_np = min(
            max(profile_np, cur_np * 2, 1024),
            8192,
        )
        if target_np > cur_np:
            suggested_settings['num_predict'] = target_np
            changes.append(
                f'Benchmark hit num_predict cap — raise to at least {target_np}'
            )

    timeouts = _timeout_cases(cases)
    if timeouts:
        gaps.append(f'{len(timeouts)} prompt(s) timed out — model may be under-provisioned or num_ctx too large for VRAM')
        changes.append(
            'Enable COPILOT_PREWARM_ON_START and COPILOT_KEEP_ALIVE to avoid reload stalls between agent turns'
        )

    failed = _failed_categories(cases)
    if failed.get('reasoning') and model_uses_thinking(model_name):
        if client.get('copilot_think') == 'on':
            suggested_client['copilot_think'] = 'off'
            changes.append(
                'Reasoning failures with think:on — use copilot_think=off for concise factual replies'
            )

    if failed.get('instruction') or failed.get('creativity'):
        if not client.get('context_trim_enabled', True):
            suggested_client['context_trim_enabled'] = True
            changes.append('Enable context_trim so instruction-following stays stable in long threads')

    if baseline is not None:
        lift = float(benchmark.get('overall_score', 0)) - float(baseline.get('overall_score', 0))
        if lift >= 25:
            gaps.append(f'Dashboard settings lift +{lift:.0f} vs raw Ollama — proxy is required for this model')

    if not client.get('context_trim_enabled', True):
        suggested_client['context_trim_enabled'] = True
        changes.append('Turn on context_trim for long agent sessions (keeps num_ctx budget stable)')

    agentic = _build_agentic_recommendations(
        model_name,
        current_settings=current,
        profile_settings=profile,
        client_extras=client,
        model_info=model_info,
        benchmark=benchmark,
        baseline=baseline,
    )

    for key, value in agentic.get('settings', {}).items():
        if key not in suggested_settings and current.get(key) != value:
            if key == 'num_ctx' and int(current.get(key) or 0) < int(value):
                suggested_settings[key] = value
            if key == 'num_predict' and int(current.get(key) or 0) < int(value):
                suggested_settings[key] = value

    status = _validation_status(
        benchmark,
        suggested_settings=suggested_settings,
        suggested_client=suggested_client,
    )

    return {
        'model': model_name,
        'validation': {
            'status': status,
            'source': settings_source,
            'overall_score': benchmark.get('overall_score', 0),
            'passed': f'{benchmark.get("passed_count", 0)}/{benchmark.get("total_count", 0)}',
            'completion_rate': benchmark.get('completion_rate', 0),
            'error_count': benchmark.get('error_count', 0),
            'current': benchmark_options_summary(current),
            'profile': benchmark_options_summary(profile),
            'drift': drift,
            'gaps': gaps,
            'failed_categories': failed,
        },
        'suggested_settings': suggested_settings,
        'suggested_client': suggested_client,
        'changes': changes,
        'agentic': agentic,
    }


def build_fleet_improvements_report(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize per-model improvement advice across the fleet."""
    if not analyses:
        return {
            'summary': 'No benchmark analyses available.',
            'models': [],
            'fleet_actions': [],
        }

    fleet_actions: list[str] = []
    critical = [a for a in analyses if a.get('validation', {}).get('status') == 'critical']
    tuning = [a for a in analyses if a.get('validation', {}).get('status') == 'needs_tuning']

    if critical:
        fleet_actions.append(
            'Critical: ' + ', '.join(
                f'{a["model"]} ({a["validation"].get("error_count", 0)} errors)'
                for a in critical
            )
        )
    if tuning:
        fleet_actions.append(
            'Review settings for: ' + ', '.join(a['model'] for a in tuning)
        )

    proxy_critical = [
        a for a in analyses
        if any('proxy is required' in g for g in a.get('validation', {}).get('gaps') or [])
    ]
    if proxy_critical:
        fleet_actions.append(
            'Enforce /ollama proxy URL in all IDE configs for: '
            + ', '.join(a['model'] for a in proxy_critical)
        )

    agent_models = [
        a for a in analyses
        if 'ask_agent' in (a.get('agentic', {}).get('recommended_roles') or [])
    ]
    if agent_models:
        fleet_actions.append(
            'Agent-capable (tools): ' + ', '.join(a['model'] for a in agent_models)
            + ' — use chat + MCP, context_trim on, num_ctx >= 16k'
        )

    routing_plan = None
    try:
        from app.services.fleet_orchestration import build_fleet_routing_plan

        routing_plan = build_fleet_routing_plan(
            {'rankings': _rankings_from_analyses(analyses)},
        )
        fleet_actions.append(
            'Three-tier routing: fast='
            f'{routing_plan["routing_fast_model"]}, reasoning='
            f'{routing_plan["routing_reasoning_model"]}, coding='
            f'{routing_plan["routing_coding_model"]}'
        )
    except Exception:
        pass

    return {
        'summary': (
            f'Analyzed {len(analyses)} model(s): '
            f'{len(critical)} critical, {len(tuning)} need tuning, '
            f'{len(analyses) - len(critical) - len(tuning)} ok.'
        ),
        'models': analyses,
        'fleet_actions': fleet_actions,
        'routing_plan': routing_plan,
    }


def _rankings_from_analyses(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """Build minimal rankings block from per-model validation scores."""
    overall = sorted(
        analyses,
        key=lambda a: float((a.get('validation') or {}).get('overall_score') or 0),
        reverse=True,
    )
    return {
        'overall': [
            {'model': a['model'], 'score': (a.get('validation') or {}).get('overall_score', 0)}
            for a in overall if a.get('model')
        ],
    }


def analyze_model_from_service(service, model_name: str, benchmark: dict[str, Any], baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load live settings/metadata from OllamaService and analyze benchmark."""
    from app.services.benchmark_settings import resolve_profile_benchmark_options

    entry = service.get_model_settings_with_fallback(model_name) or {}
    settings = dict(entry.get('settings') or {})
    profile_opts = resolve_profile_benchmark_options(service, model_name)

    model_info: dict[str, Any] = {'name': model_name}
    try:
        available = service.get_available_models()
        for row in available:
            if row.get('name') == model_name:
                model_info = row
                break
    except Exception:
        pass

    return analyze_benchmark_improvements(
        model_name,
        benchmark,
        current_settings=settings,
        settings_source=str(entry.get('source') or 'unknown'),
        client_extras=get_client_extras(entry),
        profile_settings=profile_opts,
        model_info=model_info,
        baseline=baseline,
    )
