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
        v = m.get('has_vision')
        assert v in (True, False, None), f"has_vision must be bool or None: {v!r}"
        v = m.get('has_tools')
        assert v in (True, False, None), f"has_tools must be bool or None: {v!r}"
        v = m.get('has_reasoning')
        assert v in (True, False, None), f"has_reasoning must be bool or None: {v!r}"


def test_best_models_capability_flags_boolean_types():
    # get_best_models returns curated list with flags
    svc = OllamaService()
    models = svc.get_best_models()
    for m in models:
        for key in ('has_vision', 'has_tools', 'has_reasoning'):
            v = m.get(key)
            assert v in (True, False, None), f"{key} must be bool or None: {v!r}"
