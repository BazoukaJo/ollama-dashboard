"""Tests for benchmark-driven settings improvement analysis."""
from app.services.benchmark_improvements import (
    analyze_benchmark_improvements,
    build_fleet_improvements_report,
)


def _benchmark(
    *,
    score=80,
    passed=6,
    total=8,
    errors=0,
    cases=None,
):
    return {
        'model': 'test:7b',
        'overall_score': score,
        'passed_count': passed,
        'total_count': total,
        'error_count': errors,
        'completion_rate': (total - errors) / total if total else 0,
        'avg_response_time': 5.0,
        'cases': cases or [],
    }


def test_suggests_num_predict_on_truncation():
    cases = [{
        'id': 'capitals_alpha',
        'category': 'knowledge',
        'status': 'success',
        'passed': False,
        'notes': ['likely truncated at num_predict=256'],
    }]
    result = analyze_benchmark_improvements(
        'qwen3:8b',
        _benchmark(cases=cases),
        current_settings={'num_predict': 256, 'num_ctx': 8192},
        profile_settings={'num_predict': 8192, 'num_ctx': 16384},
    )
    assert result['suggested_settings'].get('num_predict', 0) >= 512
    assert any('num_predict' in c for c in result['changes'])


def test_flags_proxy_required_from_baseline_lift():
    baseline = _benchmark(score=25, passed=2)
    dashboard = _benchmark(score=95, passed=8)
    result = analyze_benchmark_improvements(
        'qwen3.6:35b-fast',
        dashboard,
        current_settings={'num_predict': 8192, 'num_ctx': 32768},
        profile_settings={'num_predict': 8192},
        baseline=baseline,
    )
    assert any('proxy is required' in g for g in result['validation']['gaps'])


def test_agentic_recommends_tools_role():
    result = analyze_benchmark_improvements(
        'qwen3-coder:7b',
        _benchmark(score=90, passed=8),
        current_settings={'num_ctx': 8192, 'num_predict': 512},
        profile_settings={'num_predict': 4096, 'context_target': 16384},
        model_info={'name': 'qwen3-coder:7b', 'has_tools': True},
    )
    roles = result['agentic']['recommended_roles']
    assert 'ask_agent' in roles
    assert result['agentic']['client']['context_trim_enabled'] is True
    assert result['agentic']['settings']['num_predict'] >= 4096


def test_critical_status_on_timeouts():
    cases = [{
        'id': 'quick_math',
        'category': 'reasoning',
        'status': 'error',
        'error': 'Read timed out',
    }]
    result = analyze_benchmark_improvements(
        'gemma4:12b',
        _benchmark(errors=1, cases=cases),
        current_settings={'num_ctx': 8192},
        profile_settings={},
    )
    assert result['validation']['status'] == 'critical'
    assert any('PREWARM' in c or 'KEEP_ALIVE' in c for c in result['changes'])


def test_fleet_improvements_summary():
    analyses = [
        {'model': 'a', 'validation': {'status': 'critical', 'error_count': 2}},
        {'model': 'b', 'validation': {'status': 'ok'}},
    ]
    fleet = build_fleet_improvements_report(analyses)
    assert '1 critical' in fleet['summary']
    assert fleet['fleet_actions']
