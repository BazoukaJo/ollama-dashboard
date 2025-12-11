#!/usr/bin/env python
"""Test script for the running Ollama Dashboard app (skipped in CI)."""
import json
import sys
import time

import pytest
import requests

pytestmark = pytest.mark.skip(reason="Integration helper; skipped in automated test runs")

BASE_URL = "http://localhost:5000"

def test_endpoint(name, url, method='GET', data=None, expected_status=200):
    """Test an endpoint and return True if successful."""
    try:
        if method == 'GET':
            response = requests.get(url, timeout=5)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=5)
        else:
            response = requests.request(method, url, json=data, timeout=5)

        if response.status_code == expected_status:
            print(f"✓ {name}: {response.status_code}")
            return True, response
        else:
            print(f"✗ {name}: Expected {expected_status}, got {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return False, response
    except requests.exceptions.ConnectionError:
        print(f"✗ {name}: Connection refused - is the app running?")
        return False, None
    except Exception as e:
        print(f"✗ {name}: Error - {e}")
        return False, None

def main():
    """Test all endpoints of the running app."""
    print("=" * 60)
    print("Testing Ollama Dashboard App")
    print("=" * 60)
    print()

    results = []

    # Test ping endpoint
    success, resp = test_endpoint("Ping", f"{BASE_URL}/ping")
    results.append(("Ping", success))
    if resp:
        print(f"  Response: {resp.json()}")

    print()

    # Test health endpoint
    success, resp = test_endpoint("Health Check", f"{BASE_URL}/api/health")
    results.append(("Health", success))
    if resp and resp.status_code == 200:
        data = resp.json()
        print(f"  Status: {data.get('status')}")
        print(f"  Background thread: {data.get('background_thread_alive')}")
        print(f"  Running models: {data.get('models', {}).get('running_count', 0)}")
        print(f"  Available models: {data.get('models', {}).get('available_count', 0)}")

    print()

    # Test system stats
    success, resp = test_endpoint("System Stats", f"{BASE_URL}/api/system/stats")
    results.append(("System Stats", success))
    if resp and resp.status_code == 200:
        data = resp.json()
        print(f"  CPU: {data.get('cpu_percent', 0):.1f}%")
        print(f"  Memory: {data.get('memory', {}).get('percent', 0):.1f}%")
        print(f"  Disk: {data.get('disk', {}).get('percent', 0):.1f}%")

    print()

    # Test available models
    success, resp = test_endpoint("Available Models", f"{BASE_URL}/api/models/available")
    results.append(("Available Models", success))
    if resp and resp.status_code == 200:
        data = resp.json()
        models = data.get('models', [])
        print(f"  Found {len(models)} available models")
        if models:
            print(f"  Sample: {models[0].get('name', 'Unknown')}")

    print()

    # Test running models
    success, resp = test_endpoint("Running Models", f"{BASE_URL}/api/models/running")
    results.append(("Running Models", success))
    if resp and resp.status_code == 200:
        models = resp.json() if isinstance(resp.json(), list) else resp.json().get('models', [])
        print(f"  Found {len(models)} running models")

    print()

    # Test service status
    success, resp = test_endpoint("Service Status", f"{BASE_URL}/api/service/status")
    results.append(("Service Status", success))
    if resp and resp.status_code == 200:
        data = resp.json()
        print(f"  Status: {data.get('status')}")
        print(f"  Running: {data.get('running', False)}")

    print()

    # Test version endpoint
    success, resp = test_endpoint("Version", f"{BASE_URL}/api/version")
    results.append(("Version", success))
    if resp and resp.status_code == 200:
        data = resp.json()
        print(f"  Ollama version: {data.get('version', 'Unknown')}")

    print()

    # Test index page
    success, resp = test_endpoint("Index Page", f"{BASE_URL}/")
    results.append(("Index Page", success))
    if resp and resp.status_code == 200:
        print(f"  Page loaded: {len(resp.text)} bytes")

    print()
    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    passed = sum(1 for _, s in results if s)
    total = len(results)

    for name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"  {status}: {name}")

    print()
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed! App is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
        return 1

if __name__ == '__main__':
    sys.exit(main())

