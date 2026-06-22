#!/usr/bin/env python3
"""Multi-round benchmark → apply tuning → re-test until fleet quality stabilizes.

Runs dashboard vs baseline compare, applies suggested settings + fleet routing,
and repeats up to --max-rounds (default 3).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_OUT = _ROOT / 'data' / 'benchmark_tune_history.json'
_NUM_PREDICT_CAP = 8192


def _cap_settings(suggested: dict) -> dict:
    out = dict(suggested)
    np = out.get('num_predict')
    if isinstance(np, (int, float)) and int(np) > _NUM_PREDICT_CAP:
        out['num_predict'] = _NUM_PREDICT_CAP
    return out


def _apply_round(svc, report: dict) -> list[str]:
    from app.services.copilot_extras import normalize_client_extras
    from app.services.fleet_orchestration import (
        apply_routing_to_default_model,
        build_fleet_routing_plan,
    )

    applied: list[str] = []
    improvements = report.get('improvements') or {}
    for row in improvements.get('models') or []:
        name = row.get('model')
        suggested = row.get('suggested_settings') or {}
        suggested_client = row.get('suggested_client') or {}
        if not name:
            continue
        if not suggested and not suggested_client:
            continue
        entry = svc.get_model_settings_with_fallback(name) or {}
        merged = dict(entry.get('settings') or {})
        if suggested:
            merged.update(_cap_settings(suggested))
        client = normalize_client_extras(entry.get('client') or entry.get('copilot'))
        client.update(suggested_client)
        if svc.save_model_settings(name, merged, source='benchmark_tuned', copilot=client):
            applied.append(name)
            print(f'  Applied tuning: {name}', flush=True)

    advice = report.get('advice') or {}
    installed = [m.get('name') for m in svc.get_available_models() if m.get('name')]
    plan = build_fleet_routing_plan(advice, installed_models=installed)
    if apply_routing_to_default_model(svc, plan):
        print(
            f'  Fleet routing on {plan["routing_fast_model"]}: '
            f'fast={plan["routing_fast_model"]} '
            f'reason={plan["routing_reasoning_model"]} '
            f'code={plan["routing_coding_model"]}',
            flush=True,
        )
        applied.append('__fleet_routing__')
    return applied


def _fleet_score(report: dict) -> float:
    models = report.get('models') or []
    if not models:
        return 0.0
    scores = [float(m.get('overall_score') or 0) for m in models]
    return sum(scores) / len(scores)


def _proxy_lift(report: dict) -> float:
    comp = (report.get('proxy_advantage') or {}).get('comparisons') or []
    if not comp:
        return 0.0
    lifts = [float(c.get('lift') or 0) for c in comp]
    return sum(lifts) / len(lifts)


def _satisfied(report: dict, *, min_avg: float, min_lift: float) -> bool:
    avg = _fleet_score(report)
    lift = _proxy_lift(report)
    critical = [
        r for r in (report.get('improvements') or {}).get('models') or []
        if (r.get('validation') or {}).get('status') == 'critical'
    ]
    return avg >= min_avg and lift >= min_lift and not critical


def run_tune_loop(
    *,
    max_rounds: int = 3,
    compare: bool = True,
    min_avg_score: float = 75.0,
    min_proxy_lift: float = 10.0,
    model_names: list[str] | None = None,
    task_id: str | None = None,
) -> dict:
    os.environ.setdefault('RESIDENCY_ON_START', 'false')
    from app import create_app
    from app.services.ollama import OllamaService
    from app.services.task_tracker import complete_task, create_task, fail_task, update_task

    app = create_app()
    svc = OllamaService()
    svc.init_app(app)

    if not svc.get_service_status():
        raise RuntimeError('Ollama is not running')

    if not task_id:
        task_id = create_task(
            'benchmark_tune_loop',
            label='Benchmark tune loop',
            total_steps=max_rounds,
        )
    history: list[dict] = []
    best_report: dict | None = None
    best_score = -1.0

    try:
        with app.app_context():
            for round_num in range(1, max_rounds + 1):
                update_task(
                    task_id,
                    step=round_num - 1,
                    message=f'Round {round_num}/{max_rounds}: running fleet benchmark…',
                    percent=int(100 * (round_num - 1) / max_rounds),
                )
                print(f'\n=== Tune round {round_num}/{max_rounds} ===', flush=True)
                report = svc.run_all_model_benchmarks(
                    model_names=model_names,
                    compare_baseline=compare,
                )
                avg = _fleet_score(report)
                lift = _proxy_lift(report)
                print(f'  Fleet avg score: {avg:.1f}  proxy lift: {lift:+.1f}', flush=True)

                round_record = {
                    'round': round_num,
                    'avg_score': round(avg, 1),
                    'proxy_lift': round(lift, 1),
                    'timestamp': time.time(),
                }
                history.append(round_record)

                if avg > best_score and len(report.get('models') or []) >= len(model_names or []):
                    best_score = avg
                    best_report = report
                elif best_report is None:
                    best_score = avg
                    best_report = report

                update_task(
                    task_id,
                    message=f'Round {round_num}: applying improvements…',
                )
                _apply_round(svc, report)

                if _satisfied(report, min_avg=min_avg_score, min_lift=min_proxy_lift):
                    print('  Satisfied — stopping early.', flush=True)
                    round_record['stopped'] = 'satisfied'
                    break

        payload = {
            'history': history,
            'best_avg_score': best_score,
            'report': best_report,
            'task_id': task_id,
        }
        complete_task(task_id, {'rounds': len(history), 'best_avg_score': best_score})
        return payload
    except Exception as exc:
        fail_task(task_id, str(exc))
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Multi-round benchmark tune loop')
    parser.add_argument('--max-rounds', type=int, default=3)
    parser.add_argument('--min-avg', type=float, default=75.0)
    parser.add_argument('--min-lift', type=float, default=10.0)
    parser.add_argument('--no-compare', action='store_true')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--models', nargs='*', help='Optional subset of model tags')
    args = parser.parse_args(argv)

    try:
        payload = run_tune_loop(
            max_rounds=args.max_rounds,
            compare=not args.no_compare,
            min_avg_score=args.min_avg,
            min_proxy_lift=args.min_lift,
            model_names=args.models,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report = payload.get('report') or {}
    slim = {
        'history': payload.get('history'),
        'best_avg_score': payload.get('best_avg_score'),
        'task_id': payload.get('task_id'),
        'models': [
            {
                'model': m.get('model'),
                'score': m.get('overall_score'),
                'passed': f'{m.get("passed_count")}/{m.get("total_count")}',
                'improvements': m.get('improvements'),
            }
            for m in report.get('models') or []
        ],
        'proxy_advantage': report.get('proxy_advantage'),
        'improvements': report.get('improvements'),
        'advice': report.get('advice'),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(slim, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nWrote {args.out}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
