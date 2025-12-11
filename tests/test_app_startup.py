#!/usr/bin/env python
"""Quick test script to verify app startup and basic functionality."""
import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app

def test_app_startup():
    """Test that the app can be created and basic routes work."""
    print("Testing app startup...")
    
    try:
        app = create_app()
        app.config['TESTING'] = True
        print("✓ App created successfully")
        
        with app.test_client() as client:
            # Test ping endpoint
            resp = client.get('/ping')
            assert resp.status_code == 200
            print("✓ Ping endpoint works")
            
            # Test health endpoint
            resp = client.get('/api/health')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'status' in data
            assert 'background_thread_alive' in data
            print("✓ Health endpoint works")
            
            # Test system stats endpoint
            resp = client.get('/api/system/stats')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'cpu_percent' in data
            print("✓ System stats endpoint works")
            
            # Test available models endpoint
            resp = client.get('/api/models/available')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'models' in data
            print("✓ Available models endpoint works")
            
            # Test running models endpoint
            resp = client.get('/api/models/running')
            assert resp.status_code == 200
            print("✓ Running models endpoint works")
            
            # Test service status endpoint
            resp = client.get('/api/service/status')
            assert resp.status_code == 200
            print("✓ Service status endpoint works")
            
        print("\n✅ All basic endpoint tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_app_startup()
    sys.exit(0 if success else 1)

