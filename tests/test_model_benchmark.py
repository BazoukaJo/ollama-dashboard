"""Unit tests for model benchmark scoring (no live Ollama required)."""
from app.services.model_benchmark import (
    BENCHMARK_CASES,
    _aggregate_case_results,
    build_fleet_advice,
    build_proxy_advantage_report,
    score_bugfix_sum,
    score_capitals_alpha,
    score_gold_symbol,
    score_json_version,
    score_pirate_blockchain,
    score_python_palindrome,
    score_quick_math,
    score_reverse_ollama,
    score_sheep_riddle,
    score_speed_ready,
    score_unit_test_assert,
)


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


def test_bugfix_sum_correct():
    code = (
        'def sum_to_n(n):\n'
        '    return n * (n + 1) // 2\n'
    )
    assert score_bugfix_sum(code)['passed']


def test_json_version_extract():
    assert score_json_version('2.1')['passed']


def test_unit_test_assert_minimal():
    code = (
        'def test_palindrome_basic():\n'
        '    assert is_palindrome("aba") is True\n'
    )
    assert score_unit_test_assert(code)['passed']


def test_benchmark_suite_has_eleven_cases():
    assert len(BENCHMARK_CASES) == 11
    ids = {c.id for c in BENCHMARK_CASES}
    assert 'sheep_riddle' in ids
    assert 'python_palindrome' in ids
    assert 'bugfix_sum' in ids
    assert 'json_version' in ids


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


def test_aggregate_counts_errors_as_zero():
    cases = [
        {'status': 'success', 'score': 100, 'weight': 1.0, 'category': 'reasoning', 'passed': True,
         'tokens_per_second': 40, 'response_time': 1.0},
        {'status': 'error', 'weight': 1.0, 'category': 'coding', 'score': 0},
    ]
    agg = _aggregate_case_results(cases)
    assert agg['overall_score'] == 50.0
    assert agg['error_count'] == 1
    assert agg['completion_rate'] == 0.5


def test_quick_math_boxed_answer():
    assert score_quick_math('\\boxed{437}')['passed']


def test_sheep_riddle_ignores_thinking_prefix():
    text = 'The answer is 17 but wait 9\n9'
    assert score_sheep_riddle(text)['passed']


def test_build_proxy_advantage_report():
    dashboard = [{'model': 'qwen3:8b', 'overall_score': 95, 'passed_count': 8, 'error_count': 0}]
    baseline = [{'model': 'qwen3:8b', 'overall_score': 30, 'passed_count': 2, 'error_count': 0}]
    report = build_proxy_advantage_report(dashboard, baseline)
    assert report['comparisons'][0]['lift'] == 65.0
    assert report['comparisons'][0]['settings_critical']
    assert report['recommendations']


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
