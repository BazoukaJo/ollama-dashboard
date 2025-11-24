import json
from app import create_app
from app.services.ollama import OllamaService


def test_migrate_endpoint_removed(tmp_path):
    app = create_app()
    client = app.test_client()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)
    resp = client.post('/api/models/settings/migrate')
    assert resp.status_code == 410
    data = resp.get_json()
    assert data['success'] is False
    assert 'no longer supported' in data['message'].lower()


def test_reset_endpoint(tmp_path):
    app = create_app()
    client = app.test_client()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    resp = client.post('/api/models/settings/reset-me/reset')
    assert resp.status_code == 200
    assert resp.get_json()['success']