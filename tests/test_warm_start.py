"""Tests for warm-start payload helper."""
from unittest.mock import MagicMock

from app.services.warm_start import build_warm_start_payload


def test_build_warm_start_payload_merges_settings():
    svc = MagicMock()
    svc.get_default_settings.return_value = {'temperature': 0.5}
    svc.get_model_settings_with_fallback.return_value = {
        'settings': {'num_ctx': 8192, 'temperature': 0.8},
    }
    payload = build_warm_start_payload(svc, 'llama3:latest')
    assert payload['model'] == 'llama3:latest'
    assert payload['options']['num_ctx'] == 8192
    assert payload['options']['temperature'] == 0.8
    assert payload['keep_alive'] == '24h'
