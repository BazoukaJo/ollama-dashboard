#!/usr/bin/env python3
"""Apply suggested_settings from a dual benchmark report, then re-benchmark those models."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_REPORT = _ROOT / 'data' / 'dual_benchmark_results.json'
OUT_ROUND2 = _ROOT / 'data' / 'dual_benchmark_results_round2.json'
_NUM_PREDICT_CAP = 8192


def _cap_settings(suggested: dict) -> dict:
    out = dict(suggested)
    np = out.get('num_predict')
    if isinstance(np, (int, float)) and int(np) > _NUM_PREDICT_CAP:
        out['num_predict'] = _NUM_PREDICT_CAP
    return out


def apply_suggestions(report_path: Path) -> list[str]:
    from app import create_app
    from app.services.ollama import OllamaService

    payload = json.loads(report_path.read_text(encoding='utf-8'))
    improvements = payload.get('improvements') or {}
    applied: list[str] = []

    app = create_app()
    svc = OllamaService()
    svc.init_app(app)

    with app.app_context():
        for row in improvements.get('models') or []:
            name = row.get('model')
            suggested = row.get('suggested_settings') or {}
            suggested_client = row.get('suggested_client') or {}
            if not name or (not suggested and not suggested_client):
                continue
            capped = _cap_settings(suggested) if suggested else {}
            entry = svc.get_model_settings_with_fallback(name) or {}
            merged = dict(entry.get('settings') or {})
            merged.update(capped)
            if svc.save_model_settings(
                name, merged, source='benchmark_tuned',
                copilot=suggested_client if suggested_client else None,
            ):
                applied.append(name)
                print(
                    f'Applied to {name}: settings={json.dumps(capped)} client={json.dumps(suggested_client)}',
                    flush=True,
                )
    return applied


def rerun_models(model_names: list[str]) -> dict:
    from app import create_app
    from app.services.ollama import OllamaService

    app = create_app()
    svc = OllamaService()
    svc.init_app(app)
    with app.app_context():
        return svc.run_all_model_benchmarks(model_names=model_names, compare_baseline=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Apply benchmark improvements and re-test')
    parser.add_argument('--report', type=Path, default=DEFAULT_REPORT)
    parser.add_argument('--apply-only', action='store_true')
    parser.add_argument('--rerun-only', nargs='*', metavar='MODEL')
    args = parser.parse_args(argv)

    if args.rerun_only is not None and args.rerun_only:
        names = list(args.rerun_only)
    else:
        if not args.report.is_file():
            print(f'Missing report: {args.report}', file=sys.stderr)
            return 1
        names = apply_suggestions(args.report)
        if not names:
            print('No suggested_settings to apply.', flush=True)
            if args.apply_only:
                return 0

    if args.apply_only:
        return 0

    if not names:
        return 0

    print(f'Re-benchmarking {len(names)} tuned model(s)...', flush=True)
    payload = rerun_models(names)
    OUT_ROUND2.parent.mkdir(parents=True, exist_ok=True)
    OUT_ROUND2.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {OUT_ROUND2}', flush=True)

    for row in payload.get('models') or []:
        imp = row.get('improvements', {}).get('validation', {})
        print(
            f'  {row.get("model")}: {row.get("overall_score")}/100 '
            f'passed {row.get("passed_count")}/{row.get("total_count")} '
            f'[{imp.get("status", "?")}]',
            flush=True,
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
