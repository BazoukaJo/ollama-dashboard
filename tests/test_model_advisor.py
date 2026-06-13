"""Tests for model advisor."""
from app.services.model_advisor import advise_from_hardware


def test_advise_mid_tier():
    rec = advise_from_hardware(vram_total_mb=11000, ram_total_mb=16000)
    assert rec['tier'] == 'mid'
    assert rec['num_ctx'] >= 8192
    assert rec['recommended_models']


def test_advise_cpu_tier():
    rec = advise_from_hardware(vram_total_mb=0, ram_total_mb=8000)
    assert rec['tier'] == 'cpu'
