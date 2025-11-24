#!/usr/bin/env python3
"""
Manual verification script for capability detection and display.
Run this after starting the Flask app to verify all capabilities work.
"""

import requests
import json
from typing import Dict, List

BASE_URL = "http://127.0.0.1:5000"

def test_endpoint(name: str, url: str) -> Dict:
    """Test an API endpoint and return results."""
    print(f"\n{'=' * 60}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print('=' * 60)

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}

def analyze_capabilities(models: List[Dict]) -> Dict:
    """Analyze capability distribution in model list."""
    vision_count = sum(1 for m in models if m.get('has_vision'))
    tools_count = sum(1 for m in models if m.get('has_tools'))
    reasoning_count = sum(1 for m in models if m.get('has_reasoning'))

    return {
        "total": len(models),
        "vision": vision_count,
        "tools": tools_count,
        "reasoning": reasoning_count
    }

def verify_model_structure(model: Dict) -> bool:
    """Verify model has required capability fields."""
    required = ['has_vision', 'has_tools', 'has_reasoning']
    return all(field in model for field in required)

def main():
    print("\n" + "=" * 60)
    print("CAPABILITY DETECTION VERIFICATION SCRIPT")
    print("=" * 60)

    # Test 1: Downloadable models (best)
    result = test_endpoint(
        "Downloadable Models (Best)",
        f"{BASE_URL}/api/models/downloadable?category=best"
    )
    if result["success"]:
        models = result["data"]["models"]
        stats = analyze_capabilities(models)
        print(f"\n✓ Found {stats['total']} models")
        print(f"  - Vision models: {stats['vision']}")
        print(f"  - Tools models: {stats['tools']}")
        print(f"  - Reasoning models: {stats['reasoning']}")

        # Verify llava has vision
        llava = next((m for m in models if m['name'] == 'llava'), None)
        if llava and llava.get('has_vision'):
            print(f"\n✓ Llava correctly flagged with vision capability")
        else:
            print(f"\n✗ ERROR: Llava missing vision capability!")
    else:
        print(f"\n✗ FAILED: {result['error']}")

    # Test 2: Downloadable models (all)
    result = test_endpoint(
        "Downloadable Models (All)",
        f"{BASE_URL}/api/models/downloadable?category=all"
    )
    if result["success"]:
        models = result["data"]["models"]
        stats = analyze_capabilities(models)
        print(f"\n✓ Found {stats['total']} models")
        print(f"  - Vision models: {stats['vision']}")
        print(f"  - Tools models: {stats['tools']}")
        print(f"  - Reasoning models: {stats['reasoning']}")

        # Verify all models have capability fields
        missing = [m['name'] for m in models if not verify_model_structure(m)]
        if not missing:
            print(f"\n✓ All models have complete capability structure")
        else:
            print(f"\n✗ ERROR: Models missing capability fields: {', '.join(missing)}")
    else:
        print(f"\n✗ FAILED: {result['error']}")

    # Test 3: Available models
    result = test_endpoint(
        "Available Models",
        f"{BASE_URL}/api/models/available"
    )
    if result["success"]:
        models = result["data"]["models"]
        if models:
            stats = analyze_capabilities(models)
            print(f"\n✓ Found {stats['total']} available models")
            print(f"  - Vision models: {stats['vision']}")
            print(f"  - Tools models: {stats['tools']}")
            print(f"  - Reasoning models: {stats['reasoning']}")
        else:
            print(f"\n✓ No models currently available (Ollama may not be running)")
    else:
        print(f"\n✗ FAILED: {result['error']}")

    # Test 4: Running models
    result = test_endpoint(
        "Running Models",
        f"{BASE_URL}/api/models/running"
    )
    if result["success"]:
        models = result["data"]
        if isinstance(models, list):
            if models:
                stats = analyze_capabilities(models)
                print(f"\n✓ Found {stats['total']} running models")
                print(f"  - Vision models: {stats['vision']}")
                print(f"  - Tools models: {stats['tools']}")
                print(f"  - Reasoning models: {stats['reasoning']}")

                # Show first model as example
                print(f"\nExample model structure:")
                print(f"  Name: {models[0].get('name')}")
                print(f"  has_vision: {models[0].get('has_vision')}")
                print(f"  has_tools: {models[0].get('has_tools')}")
                print(f"  has_reasoning: {models[0].get('has_reasoning')}")
            else:
                print(f"\n✓ No models currently running")
        else:
            print(f"\n✗ ERROR: Unexpected response format")
    else:
        print(f"\n✗ FAILED: {result['error']}")

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Open http://127.0.0.1:5000 in your browser")
    print("2. Check that capability icons display correctly:")
    print("   🧠 Brain icon = Reasoning capability")
    print("   🖼️  Image icon = Vision capability")
    print("   🔧 Tools icon = Tool usage capability")
    print("3. Icons should be colored/enabled for capable models")
    print("4. Icons should be gray/disabled for non-capable models")

if __name__ == '__main__':
    main()
