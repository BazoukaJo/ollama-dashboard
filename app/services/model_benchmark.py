"""Objective benchmark suite for installed Ollama models.

Prompts are playful but scored with deterministic checks so rankings reflect
real capability (reasoning, coding, knowledge, instruction-following, speed).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from app.services.service_errors import HTTP_SERVICE_ERRORS

# European capitals (subset — enough to validate list exercises)
_EUROPEAN_CAPITALS = frozenset({
    'amsterdam', 'athens', 'berlin', 'brussels', 'bucharest', 'budapest',
    'copenhagen', 'dublin', 'helsinki', 'lisbon', 'london', 'madrid', 'oslo',
    'paris', 'prague', 'rome', 'stockholm', 'vienna', 'warsaw', 'zagreb',
    'belgrade', 'bern', 'kyiv', 'kiev', 'moscow', 'ankara', 'reykjavik',
    'luxembourg', 'monaco', 'vaduz', 'san marino', 'andorra la vella',
    'nicosia', 'valletta', 'tirana', 'skopje', 'podgorica', 'sarajevo',
    'chisinau', 'riga', 'vilnius', 'tallinn',
})


def _strip_model_artifacts(text: str) -> str:
    """Remove thinking blocks and markdown fences before scoring."""
    if not text:
        return ''
    cleaned = re.sub(
        r'<\s*think\s*>.*?<\s*/\s*think\s*>',
        '',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(r'<\s*/\s*think\s*>\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'```[\w]*\s*', '', cleaned)
    cleaned = cleaned.replace('```', '')
    return cleaned.strip()


def _first_integer(text: str) -> int | None:
    match = re.search(r'-?\d+', text or '')
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'[.!?]+', text or '')
    return [p.strip() for p in parts if p.strip()]


def score_sheep_riddle(response: str) -> dict[str, Any]:
    text = _strip_model_artifacts(response)
    value = _first_integer(text)
    passed = value == 9
    return {
        'score': 100 if passed else (35 if value is not None else 0),
        'passed': passed,
        'notes': [] if passed else [f'expected 9, got {value!r}'],
        'expected': '9',
    }


def score_quick_math(response: str) -> dict[str, Any]:
    text = _strip_model_artifacts(response)
    value = _first_integer(text)
    passed = value == 437
    return {
        'score': 100 if passed else (40 if value is not None else 0),
        'passed': passed,
        'notes': [] if passed else [f'expected 437, got {value!r}'],
        'expected': '437',
    }


def score_gold_symbol(response: str) -> dict[str, Any]:
    text = _strip_model_artifacts(response).strip().lower()
    text = re.sub(r'[^a-z]', '', text)
    passed = text == 'au'
    return {
        'score': 100 if passed else (50 if 'au' in text else 0),
        'passed': passed,
        'notes': [] if passed else [f'expected Au, got {text!r}'],
        'expected': 'Au',
    }


def score_reverse_ollama(response: str) -> dict[str, Any]:
    text = _strip_model_artifacts(response).lower()
    text = re.sub(r'\s+', '', text)
    passed = text == 'amallo'
    return {
        'score': 100 if passed else (60 if text.endswith('amallo') or text.startswith('amallo') else 0),
        'passed': passed,
        'notes': [] if passed else [f'expected amallo, got {text!r}'],
        'expected': 'amallo',
    }


def score_pirate_blockchain(response: str) -> dict[str, Any]:
    text = _strip_model_artifacts(response)
    sentences = _split_sentences(text)
    notes: list[str] = []
    score = 0
    if len(sentences) == 2:
        score += 40
    else:
        notes.append(f'expected 2 sentences, found {len(sentences)}')
    treasure_ok = sum(1 for s in sentences if 'treasure' in s.lower())
    hash_ok = sum(1 for s in sentences if 'hash' in s.lower())
    if treasure_ok == 2:
        score += 30
    else:
        notes.append('treasure should appear in both sentences')
    if hash_ok == 2:
        score += 30
    else:
        notes.append('hash should appear in both sentences')
    passed = score >= 90
    return {'score': min(score, 100), 'passed': passed, 'notes': notes}


def score_python_palindrome(response: str) -> dict[str, Any]:
    text = _strip_model_artifacts(response)
    notes: list[str] = []
    score = 0
    if re.search(r'def\s+is_palindrome\s*\(', text):
        score += 35
    else:
        notes.append('missing def is_palindrome(...)')
    if 'return' in text:
        score += 25
    else:
        notes.append('missing return')
    if re.search(r'\[::-1\]|==\s*|\.lower\(\)|len\s*\(', text):
        score += 40
    else:
        notes.append('no obvious palindrome check')
    passed = score >= 75
    return {'score': min(score, 100), 'passed': passed, 'notes': notes}


def score_capitals_alpha(response: str) -> dict[str, Any]:
    text = _strip_model_artifacts(response)
    line = text.splitlines()[0].strip() if text else ''
    cities = [c.strip().lower() for c in line.split(',') if c.strip()]
    notes: list[str] = []
    score = 0
    if len(cities) == 4:
        score += 30
    else:
        notes.append(f'expected 4 cities, got {len(cities)}')
    valid = [c for c in cities if c in _EUROPEAN_CAPITALS]
    if len(valid) == 4:
        score += 40
    else:
        notes.append(f'invalid or unknown capitals: {cities}')
    if cities == sorted(cities):
        score += 30
    else:
        notes.append('cities not in alphabetical order')
    passed = score >= 85
    return {'score': min(score, 100), 'passed': passed, 'notes': notes}


def score_speed_ready(response: str) -> dict[str, Any]:
    text = _strip_model_artifacts(response).strip().lower()
    passed = text == 'ready'
    return {
        'score': 100 if passed else (25 if text.startswith('ready') else 0),
        'passed': passed,
        'notes': [] if passed else [f'expected exactly "ready", got {text!r}'],
        'expected': 'ready',
    }


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    category: str
    prompt: str
    weight: float
    scorer: Callable[[str], dict[str, Any]]
    description: str = ''


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        id='sheep_riddle',
        category='reasoning',
        weight=1.2,
        description='Classic "all but N" riddle',
        prompt=(
            'Riddle time! A farmer has 17 sheep. All but 9 die. '
            'How many sheep does the farmer have left? Reply with ONLY the number.'
        ),
        scorer=score_sheep_riddle,
    ),
    BenchmarkCase(
        id='quick_math',
        category='reasoning',
        weight=1.0,
        description='Mental arithmetic under pressure',
        prompt='Quick! What is 23 × 19? Answer with just the number, nothing else.',
        scorer=score_quick_math,
    ),
    BenchmarkCase(
        id='gold_symbol',
        category='knowledge',
        weight=0.9,
        description='Basic chemistry recall',
        prompt='Pop quiz: what is the chemical symbol for gold? One word, no punctuation.',
        scorer=score_gold_symbol,
    ),
    BenchmarkCase(
        id='reverse_ollama',
        category='instruction',
        weight=1.0,
        description='Exact string transform',
        prompt=(
            'Reverse the word "ollama" letter by letter. '
            'Output ONLY the reversed letters, lowercase, no spaces.'
        ),
        scorer=score_reverse_ollama,
    ),
    BenchmarkCase(
        id='pirate_blockchain',
        category='creativity',
        weight=0.8,
        description='Creative writing with strict constraints',
        prompt=(
            'You are a pirate captain briefing your crew on blockchain. '
            'Write exactly 2 sentences. Each sentence must include both the words '
            '"treasure" and "hash". No bullet points.'
        ),
        scorer=score_pirate_blockchain,
    ),
    BenchmarkCase(
        id='python_palindrome',
        category='coding',
        weight=1.3,
        description='Small Python function',
        prompt=(
            'Write a Python function named is_palindrome that takes a string s '
            'and returns True if s is a palindrome. Output only the function code, '
            'no markdown fences or explanation.'
        ),
        scorer=score_python_palindrome,
    ),
    BenchmarkCase(
        id='capitals_alpha',
        category='knowledge',
        weight=1.0,
        description='Geography + ordering',
        prompt=(
            'List exactly 4 European capital cities in alphabetical order, '
            'comma-separated with no spaces (e.g. Berlin,London,...). No other text.'
        ),
        scorer=score_capitals_alpha,
    ),
    BenchmarkCase(
        id='speed_ready',
        category='speed',
        weight=0.6,
        description='Minimal latency reply',
        prompt='Reply with exactly the word ready and nothing else.',
        scorer=score_speed_ready,
    ),
)


def _generate_url(host: str, port: int) -> str:
    return f'http://{host}:{port}/api/generate'


def _run_single_case(
    session: requests.Session,
    generate_url: str,
    model_name: str,
    case: BenchmarkCase,
    *,
    timeout: int = 120,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'model': model_name,
        'prompt': case.prompt,
        'stream': False,
        'options': dict(options or {}),
    }
    # Keep generations short for benchmark consistency
    payload['options'].setdefault('num_predict', 256)
    payload['options'].setdefault('temperature', 0.2)

    started = time.time()
    try:
        response = session.post(generate_url, json=payload, timeout=timeout)
    except HTTP_SERVICE_ERRORS as exc:
        elapsed = time.time() - started
        return {
            'id': case.id,
            'category': case.category,
            'weight': case.weight,
            'description': case.description,
            'status': 'error',
            'error': str(exc),
            'response_time': round(elapsed, 2),
        }

    if response.status_code != 200:
        elapsed = time.time() - started
        return {
            'id': case.id,
            'category': case.category,
            'weight': case.weight,
            'description': case.description,
            'status': 'error',
            'error': f'HTTP {response.status_code}: {response.text[:200]}',
            'response_time': round(elapsed, 2),
        }

    data = response.json()
    raw_response = str(data.get('response') or '')
    eval_count = int(data.get('eval_count') or 0)
    eval_duration = int(data.get('eval_duration') or 0)
    tokens_per_second = eval_count / (eval_duration / 1e9) if eval_duration > 0 else 0.0

    scored = case.scorer(raw_response)
    elapsed = time.time() - started
    return {
        'id': case.id,
        'category': case.category,
        'weight': case.weight,
        'description': case.description,
        'status': 'success',
        'score': scored['score'],
        'passed': scored.get('passed', False),
        'notes': scored.get('notes', []),
        'expected': scored.get('expected'),
        'response_preview': _strip_model_artifacts(raw_response)[:240],
        'response_time': round(elapsed, 2),
        'tokens_generated': eval_count,
        'tokens_per_second': round(tokens_per_second, 2),
    }


def _aggregate_case_results(cases: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [c for c in cases if c.get('status') == 'success']
    if not ok:
        return {
            'overall_score': 0.0,
            'category_scores': {},
            'passed_count': 0,
            'total_count': len(cases),
            'avg_tokens_per_second': 0.0,
            'avg_response_time': 0.0,
        }

    weighted_sum = 0.0
    weight_total = 0.0
    by_category: dict[str, list[float]] = {}
    for item in ok:
        w = float(item.get('weight') or 1.0)
        score = float(item.get('score') or 0)
        weighted_sum += score * w
        weight_total += w
        cat = str(item.get('category') or 'general')
        by_category.setdefault(cat, []).append(score)

    category_scores = {
        cat: round(sum(vals) / len(vals), 1)
        for cat, vals in by_category.items()
    }
    tps = [float(c.get('tokens_per_second') or 0) for c in ok]
    rts = [float(c.get('response_time') or 0) for c in ok]

    return {
        'overall_score': round(weighted_sum / weight_total if weight_total else 0.0, 1),
        'category_scores': category_scores,
        'passed_count': sum(1 for c in ok if c.get('passed')),
        'total_count': len(cases),
        'avg_tokens_per_second': round(sum(tps) / len(tps), 2) if tps else 0.0,
        'avg_response_time': round(sum(rts) / len(rts), 2) if rts else 0.0,
    }


def run_benchmark_for_model(
    session: requests.Session,
    host: str,
    port: int,
    model_name: str,
    *,
    cases: tuple[BenchmarkCase, ...] | None = None,
    timeout: int = 120,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the full (or custom) benchmark suite against one model."""
    suite = cases or BENCHMARK_CASES
    generate_url = _generate_url(host, port)
    case_results = [
        _run_single_case(session, generate_url, model_name, case, timeout=timeout, options=options)
        for case in suite
    ]
    agg = _aggregate_case_results(case_results)
    errors = [c for c in case_results if c.get('status') == 'error']
    status = 'success' if not errors else ('partial' if agg['passed_count'] else 'error')

    return {
        'model': model_name,
        'status': status,
        'cases': case_results,
        **agg,
    }


def build_fleet_advice(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize benchmark runs and suggest which models fit which jobs."""
    successful = [r for r in results if r.get('status') in ('success', 'partial')]
    if not successful:
        return {
            'summary': 'No models completed the benchmark. Is Ollama running?',
            'recommendations': [],
            'rankings': {},
        }

    by_overall = sorted(successful, key=lambda r: r.get('overall_score', 0), reverse=True)
    by_speed = sorted(successful, key=lambda r: r.get('avg_tokens_per_second', 0), reverse=True)

    categories = ('reasoning', 'coding', 'knowledge', 'instruction', 'creativity', 'speed')
    best_per_category: dict[str, dict[str, Any]] = {}
    for cat in categories:
        best_model = None
        best_score = -1.0
        for row in successful:
            score = float((row.get('category_scores') or {}).get(cat, 0))
            if score > best_score:
                best_score = score
                best_model = row.get('model')
        if best_model and best_score > 0:
            best_per_category[cat] = {'model': best_model, 'score': best_score}

    recommendations: list[str] = []
    if by_overall:
        top = by_overall[0]
        recommendations.append(
            f'Best all-round: {top["model"]} ({top.get("overall_score", 0):.0f}/100)'
        )
    if by_speed:
        fast = by_speed[0]
        recommendations.append(
            f'Fastest generation: {fast["model"]} '
            f'({fast.get("avg_tokens_per_second", 0):.1f} tok/s avg)'
        )
    for cat, info in best_per_category.items():
        if cat == 'speed' and by_speed:
            continue
        recommendations.append(
            f'Best {cat}: {info["model"]} ({info["score"]:.0f}/100 in {cat})'
        )

    if len(successful) >= 3:
        low = [r for r in successful if float(r.get('overall_score', 0)) < 45]
        if low:
            names = ', '.join(r['model'] for r in low)
            recommendations.append(
                f'Consider retiring or rarely using: {names} — scored below 45/100 overall'
            )

    specialist_hints: list[str] = []
    for row in successful:
        cats = row.get('category_scores') or {}
        coding = float(cats.get('coding', 0))
        reasoning = float(cats.get('reasoning', 0))
        overall = float(row.get('overall_score', 0))
        name = row.get('model', '')
        if coding >= 80 and overall >= 60:
            specialist_hints.append(f'{name} is a strong coding pick')
        if reasoning >= 85 and coding < 60:
            specialist_hints.append(f'{name} reasons well but struggles on code tasks')

    return {
        'summary': (
            f'Benchmarked {len(results)} model(s); '
            f'{len(successful)} produced scorable results.'
        ),
        'recommendations': recommendations,
        'specialist_hints': specialist_hints,
        'rankings': {
            'overall': [
                {'model': r['model'], 'score': r.get('overall_score', 0)}
                for r in by_overall
            ],
            'speed': [
                {'model': r['model'], 'tokens_per_second': r.get('avg_tokens_per_second', 0)}
                for r in by_speed
            ],
            'by_category': best_per_category,
        },
    }


def run_benchmark_all_models(
    session: requests.Session,
    host: str,
    port: int,
    model_names: list[str],
    *,
    cases: tuple[BenchmarkCase, ...] | None = None,
    timeout: int = 120,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Benchmark every model in model_names and return fleet advice."""
    results = [
        run_benchmark_for_model(
            session, host, port, name,
            cases=cases, timeout=timeout, options=options,
        )
        for name in model_names
    ]
    return {
        'models': results,
        'advice': build_fleet_advice(results),
        'benchmark_count': len(BENCHMARK_CASES if cases is None else cases),
    }
