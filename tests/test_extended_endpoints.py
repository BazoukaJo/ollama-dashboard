#!/usr/bin/env python
"""Extended endpoint testing for Ollama Dashboard (skipped in CI)."""
import json

import pytest
import requests

pytestmark = pytest.mark.skip(reason="Integration helper; skipped in automated test runs")

BASE_URL = "http://localhost:5000"

def print_section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

def test_endpoint(name, url, method='GET', data=None):
    """Test an endpoint and display results."""
    try:
        if method == 'GET':
            response = requests.get(url, timeout=10)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=10)
        else:
            response = requests.request(method, url, json=data, timeout=10)

        print(f"\n{name}:")
        print(f"  Status: {response.status_code}")

        if response.status_code == 200:
            try:
                data = response.json()
                print(f"  Response keys: {list(data.keys())[:10]}")
                if isinstance(data, dict) and 'models' in data:
                    print(f"  Models count: {len(data.get('models', []))}")
            except:
                print(f"  Response length: {len(response.text)} bytes")
        else:
            print(f"  Error: {response.text[:200]}")

        return response.status_code == 200
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    print_section("Extended Endpoint Testing")

    # Test downloadable models
    test_endpoint("Downloadable Models (best)", f"{BASE_URL}/api/models/downloadable?category=best")
    test_endpoint("Downloadable Models (all)", f"{BASE_URL}/api/models/downloadable?category=all")

    # Test model info (if models available)
    try:
        resp = requests.get(f"{BASE_URL}/api/models/available", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get('models', [])
            if models:
                model_name = models[0].get('name')
                test_endpoint(f"Model Info ({model_name})", f"{BASE_URL}/api/models/info/{model_name}")
    except:
        pass

    # Test model status
    try:
        resp = requests.get(f"{BASE_URL}/api/models/available", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get('models', [])
            if models:
                model_name = models[0].get('name')
                test_endpoint(f"Model Status ({model_name})", f"{BASE_URL}/api/models/status/{model_name}")
    except:
        pass

    # Test health endpoint structure
    print_section("Health Endpoint Detailed Structure")
    try:
        resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print("\nHealth Data Structure:")
            for key, value in data.items():
                if isinstance(value, dict):
                    print(f"  {key}: {{...}} ({len(value)} keys)")
                elif isinstance(value, list):
                    print(f"  {key}: [{len(value)} items]")
                else:
                    print(f"  {key}: {value}")
    except Exception as e:
        print(f"Error: {e}")

    # Test system stats structure
    print_section("System Stats Structure")
    try:
        resp = requests.get(f"{BASE_URL}/api/system/stats", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print("\nSystem Stats:")
            for key, value in data.items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for k, v in value.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  {key}: {value}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 60)
    print("Extended testing complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()

