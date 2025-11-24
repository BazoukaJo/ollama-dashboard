import json
from app import create_app
from app.services.ollama import OllamaService


def test_get_model_settings_endpoint_returns_recommended(tmp_path):
    app = create_app()
    client = app.test_client()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    resp = client.get('/api/models/settings/test-model')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'settings' in data
    assert data.get('source') in (None, 'recommended')


def test_post_and_get_model_settings_endpoint(tmp_path):
    app = create_app()
    client = app.test_client()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    payload = {"temperature": 0.42, "top_k": 15}
    resp = client.post('/api/models/settings/my-model', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success']

    # GET to confirm
    resp2 = client.get('/api/models/settings/my-model')
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2['settings']['temperature'] == 0.42


def test_delete_model_settings_endpoint(tmp_path):
    app = create_app()
    client = app.test_client()
    svc = OllamaService()
    svc.init_app(app)
    model_file = tmp_path / "model_settings.json"
    app.config['MODEL_SETTINGS_FILE'] = str(model_file)

    # Save via API
    payload = {"temperature": 0.3}
    client.post('/api/models/settings/remove-model', data=json.dumps(payload), content_type='application/json')
    # Delete
    resp = client.delete('/api/models/settings/remove-model')
    assert resp.status_code == 200
    assert resp.get_json()['success']
