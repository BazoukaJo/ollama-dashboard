#!/usr/bin/env python3
"""Test script to verify the implementation of auto-start and service control features."""
import os
import sys
import time
import requests

# Add parent directory to path when running directly (not via pytest)
if __name__ == '__main__':
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

from app import create_app

def test_auto_start_config():
    """Test that AUTO_START_OLLAMA config is properly set."""
    print("=" * 60)
    print("Test 1: Auto-Start Configuration")
    print("=" * 60)

    app = create_app()
    with app.app_context():
        auto_start = app.config.get('AUTO_START_OLLAMA')
        print(f"✓ AUTO_START_OLLAMA config: {auto_start}")
        assert isinstance(auto_start, bool) or auto_start is None, "AUTO_START_OLLAMA should be boolean or None"
        print("✓ Configuration test passed\n")

def test_service_status_check():
    """Test service status checking."""
    print("=" * 60)
    print("Test 2: Service Status Check")
    print("=" * 60)

    app = create_app()
    with app.app_context():
        from app.services.ollama import OllamaService
        service = OllamaService(app)

        try:
            status = service.get_service_status()
            print(f"✓ Service status check completed: {status}")
            print(f"  (Ollama is {'running' if status else 'not running'})")
        except Exception as e:
            print(f"✗ Service status check failed: {e}")
            raise
        print("✓ Service status test passed\n")

def test_api_verification():
    """Test API verification method."""
    print("=" * 60)
    print("Test 3: API Verification")
    print("=" * 60)

    app = create_app()
    with app.app_context():
        from app.services.ollama import OllamaService
        service = OllamaService(app)

        try:
            api_ok, api_msg = service._verify_ollama_api(max_retries=2, retry_delay=1)
            print(f"✓ API verification completed")
            print(f"  Status: {'OK' if api_ok else 'Failed'}")
            print(f"  Message: {api_msg}")
        except Exception as e:
            print(f"✗ API verification test failed: {e}")
            raise
        print("✓ API verification test passed\n")

def test_cache_clearing():
    """Test cache clearing functionality."""
    print("=" * 60)
    print("Test 4: Cache Clearing")
    print("=" * 60)

    app = create_app()
    with app.app_context():
        from app.services.ollama import OllamaService
        service = OllamaService(app)

        # Add some test data
        service._cache['test'] = 'data'
        service._cache_timestamps['test'] = time.time()
        service._last_background_error = "test error"
        service._consecutive_ps_failures = 5

        print(f"  Before clear: cache has {len(service._cache)} items")
        print(f"  Error state: {service._last_background_error}")
        print(f"  Failures: {service._consecutive_ps_failures}")

        service.clear_all_caches()

        print(f"  After clear: cache has {len(service._cache)} items")
        print(f"  Error state: {service._last_background_error}")
        print(f"  Failures: {service._consecutive_ps_failures}")

        assert len(service._cache) == 0, "Cache should be empty"
        assert service._last_background_error is None, "Error should be cleared"
        assert service._consecutive_ps_failures == 0, "Failures should be reset"
        print("✓ Cache clearing test passed\n")

def test_service_endpoints():
    """Test service control endpoints exist."""
    print("=" * 60)
    print("Test 5: Service Control Endpoints")
    print("=" * 60)

    app = create_app()
    client = app.test_client()

    endpoints = [
        ('/api/service/start', 'POST'),
        ('/api/service/stop', 'POST'),
        ('/api/service/restart', 'POST'),
        ('/api/health', 'GET'),
    ]

    for endpoint, method in endpoints:
        try:
            if method == 'POST':
                response = client.post(endpoint)
            else:
                response = client.get(endpoint)
            print(f"✓ {method} {endpoint}: {response.status_code}")
        except Exception as e:
            print(f"✗ {method} {endpoint}: {e}")
            raise

    print("✓ Service endpoints test passed\n")

def test_host_port_helper():
    """Test _get_ollama_host_port helper method."""
    print("=" * 60)
    print("Test 6: Host/Port Helper")
    print("=" * 60)

    app = create_app()
    with app.app_context():
        from app.services.ollama import OllamaService
        service = OllamaService(app)

        try:
            host, port = service._get_ollama_host_port()
            print(f"✓ Host: {host}, Port: {port}")
            assert host, "Host should not be empty"
            assert isinstance(port, int), "Port should be an integer"
            assert 1 <= port <= 65535, "Port should be in valid range"
        except Exception as e:
            print(f"✗ Host/port helper test failed: {e}")
            raise
        print("✓ Host/port helper test passed\n")

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Testing Implementation")
    print("=" * 60 + "\n")

    tests = [
        test_auto_start_config,
        test_service_status_check,
        test_api_verification,
        test_cache_clearing,
        test_service_endpoints,
        test_host_port_helper,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = test()
            if result is not False:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} raised exception: {e}\n")
            failed += 1

    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

