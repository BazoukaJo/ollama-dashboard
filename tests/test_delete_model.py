#!/usr/bin/env python3
"""Test script to verify the improved delete_model functionality."""

import requests
import json
import time
from app import create_app

def test_delete_model_comprehensive():
    """Test the delete_model endpoint with a complete flow."""
    # Create app and test client
    app = create_app()
    client = app.test_client()

    print("=" * 70)
    print("Testing Model Delete Functionality (Comprehensive)")
    print("=" * 70)

    # 1. Get available models
    print("\n1. Checking available models...")
    response = client.get('/api/models/available')
    data = response.get_json()
    available_models = data.get('models', []) if isinstance(data, dict) else data
    print(f"   Available models count: {len(available_models)}")

    if not available_models or len(available_models) == 0:
        print("\n   Warning: No available models. Cannot run test.")
        return False

    # Use the last/smallest model for testing (to minimize download time)
    model_name = available_models[-1]['name']
    model_size = available_models[-1].get('size', 0)
    print(f"   Selected model for testing: {model_name} ({model_size / (1024**3):.2f} GB)")

    # 2. Start the model
    print(f"\n2. Starting model '{model_name}' (to test unload during deletion)...")
    response = client.post(f'/api/models/start/{model_name}')
    start_result = response.get_json()
    print(f"   Response: success={start_result.get('success')}")

    if not start_result.get('success'):
        print(f"   Note: Model start failed ({start_result.get('message')}), but continuing with delete test...")
    else:
        # 3. Wait for model to load
        print("\n3. Waiting for model to load...")
        time.sleep(2)

        # 4. Check running models
        print("\n4. Verifying model is running...")
        response = client.get('/api/models/running')
        data = response.get_json()
        running_models = data if isinstance(data, list) else data.get('models', [])
        running_names = [m.get('name') for m in running_models]
        print(f"   Running models: {running_names}")

        if model_name in running_names:
            print(f"   ✓ Model is running (in memory)")
        else:
            print(f"   Note: Model not in running list")

    # 5. Get system stats before deletion
    print("\n5. Getting system stats before deletion...")
    response = client.get('/api/system/stats')
    stats = response.get_json()
    memory_before = stats.get('memory', {}).get('used', 0) if stats else 0
    vram_before = stats.get('vram', {}).get('used', 0) if stats else 0
    print(f"   Memory used: {memory_before / (1024**3):.2f} GB")
    print(f"   VRAM used: {vram_before / (1024**3):.2f} GB")

    # 6. Count available models before deletion
    response = client.get('/api/models/available')
    data = response.get_json()
    available_before = data.get('models', []) if isinstance(data, dict) else data
    count_before = len(available_before)
    print(f"   Available models before: {count_before}")

    # 7. Test delete_model endpoint
    print(f"\n6. Deleting model '{model_name}'...")
    print("   (This will unload from memory and remove from disk)")
    response = client.delete(f'/api/models/delete/{model_name}')
    delete_result = response.get_json()
    print(f"   Response: {json.dumps(delete_result, indent=6)}")
    print(f"   Status Code: {response.status_code}")

    if not delete_result.get('success'):
        print(f"\n   Failed to delete model: {delete_result.get('message')}")
        return False

    # 8. Wait for deletion to complete
    print("\n7. Waiting for deletion to complete...")
    time.sleep(2)

    # 9. Check running models after deletion
    print("\n8. Checking running models after deletion...")
    response = client.get('/api/models/running')
    data = response.get_json()
    running_models_after = data if isinstance(data, list) else data.get('models', [])
    running_names_after = [m.get('name') for m in running_models_after]
    print(f"   Running models: {running_names_after}")

    if model_name in running_names_after:
        print(f"   Error: Model is still running!")
        return False
    else:
        print(f"   ✓ Model is no longer running (successfully unloaded)")

    # 10. Check available models after deletion
    print("\n9. Checking available models after deletion...")
    response = client.get('/api/models/available')
    data = response.get_json()
    available_after = data.get('models', []) if isinstance(data, dict) else data
    count_after = len(available_after)
    print(f"   Available models after: {count_after}")

    if any(m.get('name') == model_name for m in available_after):
        print(f"   Error: Model still in available list!")
        return False
    else:
        print(f"   ✓ Model removed from available list (count: {count_before} → {count_after})")

    # 11. Get system stats after deletion
    print("\n10. Getting system stats after deletion...")
    response = client.get('/api/system/stats')
    stats = response.get_json()
    memory_after = stats.get('memory', {}).get('used', 0) if stats else 0
    vram_after = stats.get('vram', {}).get('used', 0) if stats else 0
    print(f"   Memory used: {memory_after / (1024**3):.2f} GB")
    print(f"   VRAM used: {vram_after / (1024**3):.2f} GB")

    memory_freed = memory_before - memory_after
    vram_freed = vram_before - vram_after
    print(f"\n   Memory freed: {memory_freed / (1024**3):.2f} GB")
    print(f"   VRAM freed: {vram_freed / (1024**3):.2f} GB")

    # Final verdict
    print("\n" + "=" * 70)
    print("SUCCESS: Model deletion completed successfully!")
    print("=" * 70)
    print(f"✓ Model '{model_name}' was unloaded from memory")
    print(f"✓ Model was removed from disk")
    print(f"✓ Removed from available models list")
    if vram_freed > 0:
        print(f"✓ VRAM freed: {vram_freed / (1024**3):.2f} GB")
    print("=" * 70)
    return True

if __name__ == '__main__':
    try:
        success = test_delete_model_comprehensive()
        if not success:
            print("\n" + "=" * 70)
            print("FAILED: Model deletion test failed")
            print("=" * 70)
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
