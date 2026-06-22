"""Tests for three-tier model routing."""
from app.services.model_router import (
    resolve_routed_model,
    should_route_to_coding,
    should_route_to_reasoning,
)


def test_coding_keywords_route():
    msgs = [{'role': 'user', 'content': 'Please fix this bug in the Python function'}]
    assert should_route_to_coding(msgs)
    assert not should_route_to_reasoning(msgs)


def test_reasoning_long_prompt():
    msgs = [{'role': 'user', 'content': 'x' * 5000}]
    assert should_route_to_reasoning(msgs)


def test_resolve_coding_tier():
    payload = {'model': 'gemma4:latest', 'messages': [{'role': 'user', 'content': 'fix this bug in python'}]}
    extras = {
        'routing_enabled': True,
        'routing_fast_model': 'gemma4:latest',
        'routing_reasoning_model': 'qwen3.6:27B',
        'routing_coding_model': 'Qwen3-Coder-Next:latest',
    }
    model, reason = resolve_routed_model(payload, extras)
    assert model == 'Qwen3-Coder-Next:latest'
    assert reason == 'coding_keywords_or_codeblock'


def test_resolve_default_fast():
    payload = {'model': 'qwen3.6:35b', 'messages': [{'role': 'user', 'content': 'hello'}]}
    extras = {
        'routing_enabled': True,
        'routing_fast_model': 'gemma4:latest',
        'routing_reasoning_model': 'qwen3.6:27B',
        'routing_coding_model': 'Qwen3-Coder-Next:latest',
    }
    model, reason = resolve_routed_model(payload, extras)
    assert model == 'gemma4:latest'
    assert reason == 'default_fast'
