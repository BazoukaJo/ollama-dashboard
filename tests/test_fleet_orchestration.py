"""Tests for task tracker and fleet orchestration."""
from app.services import task_tracker as tt
from app.services.fleet_orchestration import build_fleet_routing_plan, build_residency_plan


def test_task_tracker_lifecycle():
    tid = tt.create_task('test', label='unit', total_steps=3)
    tt.update_task(tid, step=1, message='working')
    row = tt.get_task(tid)
    assert row['state'] == 'running'
    assert row['step'] == 1
    tt.complete_task(tid, {'ok': True})
    assert tt.get_task(tid)['state'] == 'done'


def test_fleet_routing_plan_from_advice():
    advice = {
        'rankings': {
            'overall': [{'model': 'gemma4:latest', 'score': 95}],
            'speed': [{'model': 'lfm2.5:latest', 'tokens_per_second': 200}],
            'by_category': {
                'reasoning': {'model': 'qwen3.6:27B', 'score': 90},
                'coding': {'model': 'Qwen3-Coder-Next:latest', 'score': 88},
            },
        },
    }
    plan = build_fleet_routing_plan(
        advice,
        installed_models=['gemma4:latest', 'qwen3.6:27B', 'Qwen3-Coder-Next:latest'],
    )
    assert plan['routing_enabled']
    assert plan['routing_fast_model'] == 'gemma4:latest'
    assert plan['routing_coding_model'] == 'Qwen3-Coder-Next:latest'


def test_residency_plan_64gb():
    plan = build_residency_plan({
        'routing_fast_model': 'gemma4:latest',
        'routing_reasoning_model': 'qwen3.6:27B',
        'routing_coding_model': 'Qwen3-Coder-Next:latest',
    })
    assert plan['RESIDENCY_FAST_MODEL'] == 'gemma4:latest'
    assert plan['RESIDENCY_HEAVY_MODEL'] == 'qwen3.6:27B'
