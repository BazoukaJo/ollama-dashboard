#!/usr/bin/env python3
"""Run fleet benchmark via OllamaService (with saved settings) and bare origin API."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OUT_PATH = _ROOT / 'data' / 'dual_benchmark_results.json'


def _save(payload: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Progress saved -> {OUT_PATH}', flush=True)


def main() -> int:
    import requests
    from app import create_app
    from app.services.model_benchmark import run_benchmark_for_model
    from app.services.ollama import OllamaService

    app = create_app()
    svc = OllamaService()
    svc.init_app(app)

    if not svc.get_service_status():
        print('Ollama is not running.', file=sys.stderr)
        return 2

    with app.app_context():
        available = svc.get_available_models()
        names = [m.get('name') for m in available if m.get('name')]
        if not names:
            print('No installed models.', file=sys.stderr)
            return 1

        host, port = svc.get_ollama_host_port()
        session = requests.Session()
        payload: dict = {
            'models': names,
            'origin_url': f'http://{host}:{port}/api/generate',
            'service_path': {'models': [], 'advice': {}},
            'origin_path': {'models': [], 'advice': {}},
        }
        _save(payload)

        for idx, name in enumerate(names, 1):
            print(f'[{idx}/{len(names)}] service path: {name}', flush=True)
            payload['service_path']['models'].append(svc.run_model_benchmark(name))
            _save(payload)

        from app.services.model_benchmark import build_fleet_advice
        payload['service_path']['advice'] = build_fleet_advice(payload['service_path']['models'])
        payload['service_path']['benchmark_count'] = 8
        _save(payload)

        for idx, name in enumerate(names, 1):
            print(f'[{idx}/{len(names)}] origin path: {name}', flush=True)
            payload['origin_path']['models'].append(
                run_benchmark_for_model(session, host, port, name)
            )
            _save(payload)

        payload['origin_path']['advice'] = build_fleet_advice(payload['origin_path']['models'])
        payload['origin_path']['benchmark_count'] = 8
        _save(payload)

    print('Done.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
