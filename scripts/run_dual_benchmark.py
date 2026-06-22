#!/usr/bin/env python3
"""Compare dashboard-backed benchmarks vs raw Ollama baseline for every installed model."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OUT_PATH = _ROOT / 'data' / 'dual_benchmark_results.json'


def _print_proxy_advantage(report: dict) -> None:
    print()
    print('=' * 72)
    print('PROXY / SETTINGS ADVANTAGE (dashboard vs raw Ollama)')
    print('=' * 72)
    print(report.get('summary', ''))
    print()
    print(f'{"Model":<28} {"Dashboard":>9} {"Baseline":>9} {"Lift":>7}  Note')
    print('-' * 72)
    for row in report.get('comparisons') or []:
        note = 'proxy critical' if row.get('settings_critical') else (
            'proxy optional' if row.get('proxy_optional') else ''
        )
        print(
            f'{row["model"]:<28} '
            f'{row.get("dashboard_score", 0):>8.0f} '
            f'{row.get("baseline_score", 0):>8.0f} '
            f'{row.get("lift", 0):>+6.0f}  {note}'
        )
    print()
    for line in report.get('recommendations') or []:
        print(f'  - {line}')


def _print_improvements(report: dict) -> None:
    print()
    print('=' * 72)
    print('SETTINGS VALIDATION & AGENTIC TUNING')
    print('=' * 72)
    print(report.get('summary', ''))
    print()
    for line in report.get('fleet_actions') or []:
        print(f'  * {line}')
    print()
    for row in report.get('models') or []:
        val = row.get('validation') or {}
        status = val.get('status', '?')
        print(f'\n{row.get("model")} [{status}] score {val.get("overall_score")} passed {val.get("passed")}')
        for change in row.get('changes') or []:
            print(f'  - {change}')
        suggested = row.get('suggested_settings') or {}
        if suggested:
            print(f'  settings: {json.dumps(suggested, ensure_ascii=False)}')
        client = row.get('suggested_client') or {}
        if client:
            print(f'  client:   {json.dumps(client, ensure_ascii=False)}')
        agentic = row.get('agentic') or {}
        for tip in (agentic.get('communication') or [])[:3]:
            print(f'  comm: {tip}')


def main() -> int:
    from app import create_app
    from app.services.ollama import OllamaService

    app = create_app()
    svc = OllamaService()
    svc.init_app(app)

    if not svc.get_service_status():
        print('Ollama is not running.', file=sys.stderr)
        return 2

    with app.app_context():
        payload = svc.run_all_model_benchmarks(compare_baseline=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {OUT_PATH}', flush=True)

    _print_proxy_advantage(payload.get('proxy_advantage') or {})
    _print_improvements(payload.get('improvements') or {})
    return 0


if __name__ == '__main__':
    sys.exit(main())
