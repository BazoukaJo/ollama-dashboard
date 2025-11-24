import os
import json
from app import create_app
from app.services.ollama import OllamaService
import tempfile


def test_save_and_load_model_settings(tmp_path):
    app = create_app()
    svc = OllamaService()
    svc.init_app(app)

    # Use a tmp file for model settings
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    # Ensure empty
    assert svc.load_model_settings() == {}

    success = svc.save_model_settings('test-model', {'temperature': 0.55, 'top_k': 20}, source='user')
    assert success

    loaded = svc.load_model_settings()
    assert 'test-model' in loaded
    entry = loaded['test-model']
    assert entry['settings']['temperature'] == 0.55
    assert entry['source'] == 'user'


# Removed global autosave toggle tests; feature deprecated.


def test_get_model_settings_auto_saves_recommended(tmp_path):
    app = create_app()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    # No entry yet
    entry = svc.get_model_settings('some-new-model')
    assert entry is not None
    assert entry['source'] == 'recommended'
    assert 'settings' in entry
    # The file should be created and entry persisted
    assert 'some-new-model' in svc.load_model_settings()


def test_recommendations_small_medium_large(tmp_path):
    app = create_app()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    # Small model heuristic
    entry_small = svc._recommend_settings_for_model({'name': 'tiny-model', 'details': {'parameter_size': '1B'}, 'has_vision': False})
    assert entry_small['temperature'] >= 0.75
    assert entry_small['num_ctx'] >= 2048

    # Medium model heuristic
    entry_med = svc._recommend_settings_for_model({'name': 'mid-model', 'details': {'parameter_size': '4B'}, 'has_vision': False})
    assert 0.65 <= entry_med['temperature'] <= 0.75
    assert entry_med['num_ctx'] >= 2048

    # Large model heuristic
    entry_large = svc._recommend_settings_for_model({'name': 'big-model', 'details': {'parameter_size': '13B'}, 'has_vision': False})
    assert entry_large['temperature'] <= 0.65
    assert entry_large['num_ctx'] >= 4096

def test_recommendations_for_vision_and_reasoning_and_tools(tmp_path):
    app = create_app()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    entry_vision = svc._recommend_settings_for_model({'name': 'llava', 'details': {'families': ['vision']}, 'has_vision': True})
    assert entry_vision['num_ctx'] >= 4096
    assert entry_vision['top_p'] >= 0.9

    entry_reason = svc._recommend_settings_for_model({'name': 'deepseek-r1', 'has_reasoning': True})
    assert entry_reason['num_ctx'] >= 4096
    assert entry_reason['temperature'] <= 0.65

    entry_tool = svc._recommend_settings_for_model({'name': 'llama3.1', 'has_tools': True})
    assert entry_tool['top_k'] <= 20


def test_delete_model_settings(tmp_path):
    app = create_app()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    svc.save_model_settings('to-delete', {'temperature': 0.7})
    assert 'to-delete' in svc.load_model_settings()
    rv = svc.delete_model_settings('to-delete')
    assert rv
    assert 'to-delete' not in svc.load_model_settings()
