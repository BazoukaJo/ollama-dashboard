from app import create_app
from app.services.ollama import OllamaService
from unittest.mock import patch
import json


def test_admin_model_defaults_page_render():
    app = create_app()
    client = app.test_client()
    resp = client.get('/admin/model-defaults')
    assert resp.status_code == 200


def test_apply_all_recommended_endpoint(tmp_path):
    app = create_app()
    client = app.test_client()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    # Mock available models
    with patch('app.services.ollama.OllamaService.get_available_models') as mock_avail:
        mock_avail.return_value = [
            {'name': 'a'},
            {'name': 'b'},
        ]
        resp = client.post('/api/models/settings/apply_all_recommended')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success']
        assert data['applied'] == 2
        # Check that the file was created and entries exist
        loaded = svc.load_model_settings()
        assert 'a' in loaded and 'b' in loaded
