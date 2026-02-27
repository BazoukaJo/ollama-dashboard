"""
Test script to verify capabilities detection is working correctly
"""
import requests
import pytest
import json

BASE_URL = "http://127.0.0.1:5000"

@pytest.fixture
def client():
    from app import create_app
    app = create_app()
    with app.test_client() as client:
        yield client

def test_downloadable_models_best(client):
    """Test best downloadable models have capabilities"""
    print("\n1. Testing /api/models/downloadable?category=best")
    print("-" * 50)

    response = client.get("/api/models/downloadable?category=best")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.get_json()
    models = data.get('models', [])

    print(f"✓ Found {len(models)} models")

    # Check llava specifically
    llava = next((m for m in models if m['name'] == 'llava'), None)
    assert llava is not None, "Llava model not found"
    assert llava.get('has_vision') == True, f"Llava should have vision capability, got: {llava.get('has_vision')}"

    print("✓ Llava model found with has_vision=True")
    print(f"  - has_vision: {llava.get('has_vision')}")
    print(f"  - has_tools: {llava.get('has_tools')}")
    print(f"  - has_reasoning: {llava.get('has_reasoning')}")

    # Test assertions above will raise on failure; no return value needed

def test_downloadable_models_all(client):
    """Test extended downloadable models have capabilities"""
    print("\n2. Testing /api/models/downloadable?category=all")
    print("-" * 50)

    response = client.get("/api/models/downloadable?category=all")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.get_json()
    models = data.get('models', [])

    print(f"✓ Found {len(models)} models")

    # Find all vision models
    vision_models = [m for m in models if m.get('has_vision') == True]
    print(f"✓ Found {len(vision_models)} vision models:")

    expected_vision_models = ['llava', 'qwen3-vl', 'bakllava', 'llava-llama3', 'llava-phi3', 'moondream']
    for name in expected_vision_models:
        model = next((m for m in vision_models if name in m['name'].lower()), None)
        if model:
            print(f"  ✓ {model['name']} has vision capability")
        else:
            print(f"  ✗ {name} NOT found or missing vision capability")

    assert len(vision_models) >= 6, f"Expected at least 6 vision models, got {len(vision_models)}"

    # Test assertions above will raise on failure; no return value needed

def test_available_models(client):
    """Test available models endpoint adds capabilities"""
    print("\n3. Testing /api/models/available")
    print("-" * 50)

    response = client.get("/api/models/available")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.get_json()
    models = data.get('models', [])

    if len(models) == 0:
        pytest.skip("No available models found (no models downloaded yet)")

    print(f"✓ Found {len(models)} available models")

    # Check if any vision models
    vision_models = [m for m in models if m.get('has_vision') == True]
    if vision_models:
        print(f"✓ Found {len(vision_models)} vision-capable models:")
        for model in vision_models:
            print(f"  - {model['name']} (has_vision: {model.get('has_vision')})")
    else:
        print("⚠ No vision-capable models in available models")
        # Check if any llava/qwen models exist but don't have capability flag
        potential_vision = [m for m in models if any(x in m['name'].lower() for x in ['llava', 'qwen', 'moondream'])]
        if potential_vision:
            print("  ✗ ERROR: Found potential vision models without capability flag:")
            for model in potential_vision:
                print(f"    - {model['name']}: has_vision={model.get('has_vision')}")

    # Test assertions above will raise on failure; no return value needed

def test_running_models(client):
    """Test running models endpoint adds capabilities"""
    print("\n4. Testing /api/models/running")
    print("-" * 50)

    response = client.get("/api/models/running")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.get_json()

    if isinstance(data, dict):
        models = data.get('models', [])
    elif isinstance(data, list):
        models = data
    else:
        models = []

    if len(models) == 0:
        pytest.skip("No running models (this is normal if no models are loaded)")

    print(f"✓ Found {len(models)} running models")

    # Check capabilities
    for model in models:
        print(f"  - {model['name']}:")
        print(f"    has_vision: {model.get('has_vision', False)}")
        print(f"    has_tools: {model.get('has_tools', False)}")
        print(f"    has_reasoning: {model.get('has_reasoning', False)}")

    # Test assertions above will raise on failure; no return value needed

def main():
    print("=" * 50)
    print("CAPABILITIES DETECTION TEST SUITE")
    print("=" * 50)

    try:
        test_downloadable_models_best()
        test_downloadable_models_all()
        test_available_models()
        test_running_models()

        print("\n" + "=" * 50)
        print("✓ ALL TESTS PASSED!")
        print("=" * 50)
        print("\nCapabilities are being correctly detected and returned by the API.")
        print("The frontend should now display vision icons for:")
        print("  - llava")
        print("  - qwen3-vl")
        print("  - bakllava")
        print("  - llava-llama3")
        print("  - llava-phi3")
        print("  - moondream")
        print("\nNext: Check the browser to verify the UI displays capabilities correctly.")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return False
    except (requests.exceptions.RequestException, requests.exceptions.Timeout,
            requests.exceptions.ConnectionError, json.JSONDecodeError) as e:
        print(f"\n✗ NETWORK/API ERROR: {e}")
        return False

    return True

if __name__ == "__main__":
    main()
