#!/usr/bin/env python3
"""Test script to verify the stop_model fix works correctly."""

import requests
import json
import time
from app import create_app

def test_stop_model():
    """Test the stop_model endpoint."""
    # Create app and test client
    app = create_app()
    client = app.test_client()

    print("=" * 60)
    print("Testing Model Stop Functionality")
    print("=" * 60)

    # 1. Get running models
    print("\n1. Checking running models...")
    response = client.get('/api/models/running')
    running_models = response.get_json()
    print(f"   Running models: {running_models}")

    if not running_models:
        print("\n   ⚠️  No running models. Test cannot proceed.")
        print("   Please start a model first using /api/models/start/<model_name>")
        return False

    model_name = running_models[0]['name'] if running_models else None
    print(f"   Selected model for testing: {model_name}")

    # 2. Test stop_model endpoint
    print(f"\n2. Stopping model '{model_name}'...")
    response = client.post(f'/api/models/stop/{model_name}')
    result = response.get_json()
    print(f"   Response: {json.dumps(result, indent=2)}")
    print(f"   Status Code: {response.status_code}")

    if not result.get('success'):
        print("\n   ❌ Failed to stop model")
        return False

    # 3. Wait a moment for unload to complete
    print("\n3. Waiting for model unload to complete...")
    time.sleep(2)

    # 4. Check running models again
    print("\n4. Checking running models after stop...")
    response = client.get('/api/models/running')
    running_models_after = response.get_json()
    print(f"   Running models: {running_models_after}")

    # Check if model was unloaded
    model_still_running = any(m.get('name') == model_name for m in running_models_after)

    if model_still_running:
        print(f"\n   ❌ Model '{model_name}' is still running after stop!")
        print("   The model was not properly unloaded from memory.")
        return False
    else:
        print(f"\n   ✅ Model '{model_name}' was successfully unloaded!")
        return True

if __name__ == '__main__':
    try:
        success = test_stop_model()
        if success:
            print("\n" + "=" * 60)
            print("✅ Test PASSED: Models are properly unloaded")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("❌ Test FAILED: Models are not properly unloading")
            print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
