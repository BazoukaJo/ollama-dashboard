"""Model benchmark tests against the Ollama origin (direct :11434 API).

Mirrors tests/test_model_benchmark.py scorer unit tests, and adds integration
checks that POST to http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/generate — not the
dashboard /ollama proxy on :5000.

Integration tests are marked ``integration`` and skipped when Ollama is down.
"""
from __future__ import annotations

import os

import pytest
import requests
from app.services.model_benchmark import (
    BENCHMARK_CASES,
    _aggregate_case_results,
    _generate_url,
    build_fleet_advice,
    run_benchmark_all_models,
    run_benchmark_for_model,
    score_capitals_alpha,
    score_gold_symbol,
    score_pirate_blockchain,
    score_python_palindrome,
    score_quick_math,
    score_reverse_ollama,
    score_sheep_riddle,
    score_speed_ready,
)


def _resolve_ollama_source_host_port() -> tuple[str, int]:
    """Ollama daemon address — never the dashboard /ollama proxy URL."""
    from app.services.ollama_core import OllamaServiceCore

    core = OllamaServiceCore.__new__(OllamaServiceCore)
    core.app = None
    return core._get_ollama_host_port()


def _origin_tags_url() -> str:
    host, port = _resolve_ollama_source_host_port()
    return f'http://{host}:{port}/api/tags'


def _origin_reachable() -> bool:
    try:
        response = requests.get(_origin_tags_url(), timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False


def _first_installed_model() -> str | None:
    response = requests.get(_origin_tags_url(), timeout=5)
    if response.status_code != 200:
        return None
    models = response.json().get('models') or []
    for entry in models:
        name = entry.get('name')
        if name:
            return str(name)
    return None


# --- Scorer unit tests (identical to tests/test_model_benchmark.py) ---


def test_sheep_riddle_correct():
    result = score_sheep_riddle('9')
    assert result['passed']
    assert result['score'] == 100


def test_sheep_riddle_wrong_number():
    result = score_sheep_riddle('8 sheep remain')
    assert not result['passed']


def test_quick_math_correct():
    assert score_quick_math('437')['passed']


def test_gold_symbol_correct():
    assert score_gold_symbol('Au')['passed']


def test_reverse_ollama_correct():
    assert score_reverse_ollama('amallo')['passed']


def test_pirate_blockchain_constraints():
    good = (
        'We guard the treasure behind a hash on the chain. '
        'Any treasure map must match the hash before we sail.'
    )
    assert score_pirate_blockchain(good)['passed']


def test_python_palindrome_minimal():
    code = (
        'def is_palindrome(s):\n'
        '    return s == s[::-1]\n'
    )
    assert score_python_palindrome(code)['passed']


def test_capitals_alpha_valid():
    text = 'Berlin,London,Madrid,Paris'
    assert score_capitals_alpha(text)['passed']


def test_speed_ready_exact():
    assert score_speed_ready('ready')['passed']
    assert not score_speed_ready('Ready!')['passed']


def test_benchmark_suite_has_eight_cases():
    assert len(BENCHMARK_CASES) == 8
    ids = {c.id for c in BENCHMARK_CASES}
    assert 'sheep_riddle' in ids
    assert 'python_palindrome' in ids


def test_aggregate_case_results_weighted():
    cases = [
        {'status': 'success', 'score': 100, 'weight': 1.0, 'category': 'reasoning', 'passed': True,
         'tokens_per_second': 40, 'response_time': 1.0},
        {'status': 'success', 'score': 50, 'weight': 2.0, 'category': 'coding', 'passed': False,
         'tokens_per_second': 20, 'response_time': 2.0},
    ]
    agg = _aggregate_case_results(cases)
    assert agg['overall_score'] == 66.7
    assert agg['passed_count'] == 1
    assert agg['category_scores']['reasoning'] == 100.0
    assert agg['avg_tokens_per_second'] == 30.0


def test_build_fleet_advice_rankings():
    results = [
        {
            'model': 'fast-small',
            'status': 'success',
            'overall_score': 55,
            'avg_tokens_per_second': 90,
            'category_scores': {'coding': 40, 'reasoning': 70},
        },
        {
            'model': 'smart-big',
            'status': 'success',
            'overall_score': 82,
            'avg_tokens_per_second': 25,
            'category_scores': {'coding': 85, 'reasoning': 90},
        },
    ]
    advice = build_fleet_advice(results)
    assert 'smart-big' in advice['recommendations'][0]
    assert advice['rankings']['overall'][0]['model'] == 'smart-big'
    assert advice['rankings']['speed'][0]['model'] == 'fast-small'


# --- Direct-origin integration (no /ollama proxy) ---


def test_origin_generate_url_is_direct_api():
    host, port = _resolve_ollama_source_host_port()
    url = _generate_url(host, port)
    assert url.endswith('/api/generate')
    assert '/ollama/' not in url
    dashboard_port = os.getenv('DASHBOARD_PORT', '5000')
    assert f':{dashboard_port}/' not in url


@pytest.mark.integration
@pytest.mark.skipif(not _origin_reachable(), reason='Ollama origin not reachable')
def test_origin_tags_endpoint():
    response = requests.get(_origin_tags_url(), timeout=5)
    assert response.status_code == 200
    assert 'models' in response.json()


@pytest.mark.integration
@pytest.mark.skipif(not _origin_reachable(), reason='Ollama origin not reachable')
def test_benchmark_single_model_via_origin():
    model_name = _first_installed_model()
    if not model_name:
        pytest.skip('no models installed at Ollama origin')

    host, port = _resolve_ollama_source_host_port()
    session = requests.Session()
    result = run_benchmark_for_model(session, host, port, model_name, path='baseline')

    assert result['model'] == model_name
    assert result['total_count'] == len(BENCHMARK_CASES)
    assert any(c.get('status') == 'success' for c in result['cases'])


@pytest.mark.integration
@pytest.mark.skipif(not _origin_reachable(), reason='Ollama origin not reachable')
def test_benchmark_all_installed_models_via_origin():
    model_name = _first_installed_model()
    if not model_name:
        pytest.skip('no models installed at Ollama origin')

    host, port = _resolve_ollama_source_host_port()
    session = requests.Session()
    payload = run_benchmark_all_models(session, host, port, [model_name])

    assert len(payload['models']) == 1
    assert payload['models'][0]['model'] == model_name
    assert payload['benchmark_count'] == len(BENCHMARK_CASES)
    assert 'advice' in payload
