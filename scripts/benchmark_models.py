#!/usr/bin/env python3
"""Run the model benchmark suite against every installed Ollama model.

Usage (from repo root, venv active):
  python scripts/benchmark_models.py
  python scripts/benchmark_models.py --model llama3.2:3b --model qwen2.5-coder:7b
  python scripts/benchmark_models.py --json-out data/benchmark_results.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _print_report(payload: dict) -> None:
    advice = payload.get('advice') or {}
    print()
    print('=' * 72)
    print('OLLAMA MODEL BENCHMARK')
    print('=' * 72)
    print(advice.get('summary', ''))
    print()

    models = payload.get('models') or []
    if not models:
        print('No models benchmarked.')
        return

    print(f'{"Model":<36} {"Score":>6} {"Pass":>6} {"tok/s":>8} {"Time":>7}')
    print('-' * 72)
    for row in sorted(models, key=lambda r: r.get('overall_score', 0), reverse=True):
        name = str(row.get('model', ''))[:35]
        score = row.get('overall_score', 0)
        passed = row.get('passed_count', 0)
        total = row.get('total_count', 0)
        tps = row.get('avg_tokens_per_second', 0)
        rt = row.get('avg_response_time', 0)
        print(f'{name:<36} {score:>5.0f} {passed}/{total:>4} {tps:>7.1f} {rt:>6.1f}s')

    print()
    print('--- Recommendations ---')
    for line in advice.get('recommendations') or []:
        print(f'  - {line}')
    for line in advice.get('specialist_hints') or []:
        print(f'  - {line}')

    print()
    print('--- Per-model breakdown ---')
    for row in sorted(models, key=lambda r: r.get('overall_score', 0), reverse=True):
        print(f'\n{row.get("model")} - {row.get("overall_score", 0):.0f}/100')
        cats = row.get('category_scores') or {}
        if cats:
            parts = [f'{k}: {v:.0f}' for k, v in sorted(cats.items())]
            print('  Categories:', ', '.join(parts))
        for case in row.get('cases') or []:
            if case.get('passed'):
                mark = 'OK'
            elif case.get('status') == 'success':
                mark = 'X'
            else:
                mark = '!'
            cid = case.get('id', '')
            sc = case.get('score', '-')
            print(f'  [{mark}] {cid}: {sc}')
            for note in case.get('notes') or []:
                print(f'       - {note}')
            if case.get('status') == 'error':
                print(f'       ! {case.get("error")}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Benchmark installed Ollama models')
    parser.add_argument(
        '--model', '-m', action='append', dest='models',
        help='Benchmark only these models (repeatable). Default: all installed.',
    )
    parser.add_argument(
        '--json-out', type=Path,
        help='Write full JSON results to this path',
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Suppress human-readable report (use with --json-out)',
    )
    args = parser.parse_args(argv)

    from app import create_app
    from app.services.ollama import OllamaService

    app = create_app()
    svc = OllamaService()
    svc.init_app(app)

    if not svc.get_service_status():
        print('benchmark_models: Ollama is not running. Start Ollama and retry.', file=sys.stderr)
        return 2

    names = args.models
    if not names:
        available = svc.get_available_models()
        names = [m.get('name') for m in available if m.get('name')]
    if not names:
        print('benchmark_models: no installed models found.', file=sys.stderr)
        return 1

    print(f'Benchmarking {len(names)} model(s) - {len(names) * 8} prompts total (approx).')
    print('This may take several minutes...')

    with app.app_context():
        payload = svc.run_all_model_benchmarks(model_names=names)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
        if not args.quiet:
            print(f'Wrote JSON to {args.json_out}')

    if not args.quiet:
        _print_report(payload)

    return 0


if __name__ == '__main__':
    sys.exit(main())
