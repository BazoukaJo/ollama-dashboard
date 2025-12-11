#!/usr/bin/env python3
"""Test script to verify the stop_model fix works correctly."""

import requests
import json
import time
from app import create_app

def test_stop_model_comprehensive():
    """Test the stop_model endpoint with a complete flow."""
    # Create app and test client
    app = create_app()
    client = app.test_client()

    print("=" * 60)
    print("Testing Model Stop Functionality (Comprehensive)")
    print("=" * 60)

    # 1. Get available models
    print("\n1. Checking available models...")
    response = client.get('/api/models/available')
    data = response.get_json()
    available_models = data.get('models', []) if isinstance(data, dict) else data
    print(f"   Available models count: {len(available_models) if isinstance(available_models, list) else 'N/A'}")

    if not available_models or len(available_models) == 0:
        print("\n   ⚠️  No available models. Cannot run test.")
        return False

    model_name = available_models[0]['name'] if isinstance(available_models, list) else None
    print(f"   Selected model for testing: {model_name}")

    # 2. Start the model
    print(f"\n2. Starting model '{model_name}'...")
    response = client.post(f'/api/models/start/{model_name}')
    start_result = response.get_json()
    print(f"   Response: {json.dumps(start_result, indent=2)}")
    print(f"   Status Code: {response.status_code}")

    if not start_result.get('success'):
        print(f"\n   ⚠️  Failed to start model: {start_result.get('message')}")
        print("   Test cannot proceed without starting a model.")
        return False

    # 3. Wait for model to load
    print("\n3. Waiting for model to load...")
    time.sleep(3)

    # 4. Check running models
    print("\n4. Checking running models after start...")
    response = client.get('/api/models/running')
    data = response.get_json()
    running_models_before = data if isinstance(data, list) else data.get('models', [])
    print(f"   Running models: {[m.get('name') for m in running_models_before]}")

    model_is_running = any(m.get('name') == model_name for m in running_models_before)
    if not model_is_running:
        print(f"\n   ⚠️  Model '{model_name}' is not running after start.")
        print("   Cannot test stop without a running model.")
        return False

    # 5. Get system stats before stop
    print("\n5. Getting system stats before stop...")
    response = client.get('/api/system/stats')
    stats_before = response.get_json()
    memory_before = stats_before.get('memory', {}).get('used', 0) if stats_before else 0
    vram_before = stats_before.get('vram', {}).get('used', 0) if stats_before else 0
    print(f"   Memory used: {memory_before / (1024**3):.2f} GB")
    print(f"   VRAM used: {vram_before / (1024**3):.2f} GB")

    # 6. Test stop_model endpoint
    print(f"\n6. Stopping model '{model_name}'...")
    response = client.post(f'/api/models/stop/{model_name}')
    result = response.get_json()
    print(f"   Response: {json.dumps(result, indent=2)}")
    print(f"   Status Code: {response.status_code}")

    if not result.get('success'):
        print(f"\n   ❌ Failed to stop model: {result.get('message')}")
        return False

    # 7. Wait for model to unload
    print("\n7. Waiting for model to unload...")
    time.sleep(2)

    # 8. Check running models again
    print("\n8. Checking running models after stop...")
    response = client.get('/api/models/running')
    data = response.get_json()
    running_models_after = data if isinstance(data, list) else data.get('models', [])
    print(f"   Running models: {[m.get('name') for m in running_models_after]}")

    model_still_running = any(m.get('name') == model_name for m in running_models_after)

    # 9. Get system stats after stop
    print("\n9. Getting system stats after stop...")
    response = client.get('/api/system/stats')
    stats_after = response.get_json()
    memory_after = stats_after.get('memory', {}).get('used', 0) if stats_after else 0
    vram_after = stats_after.get('vram', {}).get('used', 0) if stats_after else 0
    print(f"   Memory used: {memory_after / (1024**3):.2f} GB")
    print(f"   VRAM used: {vram_after / (1024**3):.2f} GB")

    memory_freed = memory_before - memory_after
    vram_freed = vram_before - vram_after
    print(f"\n   Memory freed: {memory_freed / (1024**3):.2f} GB")
    print(f"   VRAM freed: {vram_freed / (1024**3):.2f} GB")

    # 10. Final verdict
    print("\n" + "=" * 60)
    if model_still_running:
        print(f"❌ FAILED: Model '{model_name}' is still in running list after stop!")
        return False
    else:
        print(f"✅ SUCCESS: Model '{model_name}' was successfully unloaded!")
        print(f"   - Model removed from running list")
        if memory_freed > 0:
            print(f"   - Memory freed: {memory_freed / (1024**3):.2f} GB")
        if vram_freed > 0:
            print(f"   - VRAM freed: {vram_freed / (1024**3):.2f} GB")
        return True

if __name__ == '__main__':
    try:
        success = test_stop_model_comprehensive()
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Test ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
