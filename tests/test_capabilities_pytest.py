import pytest
from app.services.ollama import OllamaService

VISION_MODELS = {"llava", "llava-phi3", "llava-llama3", "bakllava", "moondream"}

@pytest.fixture(scope="module")
def service():
    svc = OllamaService()
    svc.app = None
    return svc

def test_best_models_have_expected_fields(service):
    models = service.get_best_models()
    assert models, "Expected non-empty best models list"
    required_keys = {"name", "description", "parameter_size", "size"}
    for m in models:
        assert required_keys.issubset(m.keys())

def test_all_downloadable_models_include_vision_flags(service):
    models = service.get_all_downloadable_models()
    names = {m['name'] for m in models}
    assert VISION_MODELS.issubset(names), "Missing expected vision models"
    flagged = [m for m in models if m.get('has_vision')]
    # All vision models should carry has_vision True
    flagged_names = {m['name'] for m in flagged}
    assert VISION_MODELS.issubset(flagged_names)

def test_category_best_matches_get_best_models(service):
    best_via_cat = service.get_downloadable_models('best')
    direct_best = service.get_best_models()
    assert {m['name'] for m in best_via_cat} == {m['name'] for m in direct_best}

def test_category_all_has_superset_of_best(service):
    all_models = service.get_downloadable_models('all')
    best = service.get_best_models()
    assert {m['name'] for m in best}.issubset({m['name'] for m in all_models})
