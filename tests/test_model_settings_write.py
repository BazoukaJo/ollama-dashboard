"""Tests for atomic model_settings.json writes."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from app.services.model_settings_helpers import load_model_settings, write_model_settings_file


@pytest.fixture
def mock_service(tmp_path):
    svc = MagicMock()
    svc.app = MagicMock()
    svc.app.config = {"MODEL_SETTINGS_FILE": str(tmp_path / "model_settings.json")}
    svc.logger = logging.getLogger("test_model_settings_write")
    svc._model_settings_disk_mtime = None
    return svc


def test_write_model_settings_atomic_roundtrip(mock_service, tmp_path):
    path = tmp_path / "model_settings.json"
    data = {"llama:latest": {"settings": {"temperature": 0.5}, "source": "user"}}
    assert write_model_settings_file(mock_service, data) is True
    assert path.is_file()
    # No stale collision temp files
    assert not list(tmp_path.glob("model_settings_*.tmp"))
    loaded = load_model_settings(mock_service)
    assert loaded == data


def test_write_model_settings_rejects_non_serializable(mock_service):
    bad = {"x": object()}
    assert write_model_settings_file(mock_service, bad) is False
