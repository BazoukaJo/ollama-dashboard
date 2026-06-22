"""Unit tests for model benchmark scoring (no live Ollama required)."""
from app.services.model_benchmark import (
    BENCHMARK_CASES,
    _aggregate_case_results,
    build_fleet_advice,
    score_capitals_alpha,
    score_gold_symbol,
    score_pirate_blockchain,
    score_python_palindrome,
    score_quick_math,
    score_reverse_ollama,
    score_sheep_riddle,
    score_speed_ready,
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
