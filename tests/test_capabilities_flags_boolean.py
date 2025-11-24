from app import create_app
from app.services.ollama import OllamaService

def test_available_models_capability_flags_boolean_types():
    app = create_app()
    svc = OllamaService()
    svc.init_app(app)
    models = svc.get_available_models()
    # If no models installed, skip assertions (environment dependent)
    if not models:
        return
    for m in models:
        assert isinstance(m.get('has_vision'), bool)
        assert isinstance(m.get('has_tools'), bool)
        assert isinstance(m.get('has_reasoning'), bool)


def test_best_models_capability_flags_boolean_types():
    # get_best_models returns curated list with flags
    svc = OllamaService()
    models = svc.get_best_models()
    for m in models:
        assert isinstance(m.get('has_vision'), bool)
        assert isinstance(m.get('has_tools'), bool)
        assert isinstance(m.get('has_reasoning'), bool)
