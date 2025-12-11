#!/usr/bin/env python3
"""Diagnostic script to test Ollama connection and configuration."""
import os
import sys
import requests
from app import create_app

def test_ollama_connection():
    """Test connection to Ollama with various configurations."""
    print("=" * 60)
    print("Ollama Connection Diagnostic")
    print("=" * 60)
    
    # Test 1: Check environment variables
    print("\n1. Environment Variables:")
    ollama_host = os.getenv('OLLAMA_HOST', 'localhost')
    ollama_port = os.getenv('OLLAMA_PORT', '11434')
    print(f"   OLLAMA_HOST: {ollama_host}")
    print(f"   OLLAMA_PORT: {ollama_port}")
    
    # Test 2: Check app configuration
    print("\n2. App Configuration:")
    app = create_app()
    with app.app_context():
        config_host = app.config.get('OLLAMA_HOST', 'NOT SET')
        config_port = app.config.get('OLLAMA_PORT', 'NOT SET')
        print(f"   OLLAMA_HOST: {config_host}")
        print(f"   OLLAMA_PORT: {config_port}")
    
    # Test 3: Test direct connection to localhost:11434
    print("\n3. Testing Direct Connection:")
    test_urls = [
        f"http://localhost:11434/api/tags",
        f"http://127.0.0.1:11434/api/tags",
        f"http://{ollama_host}:{ollama_port}/api/tags",
        f"http://{ollama_host}:{ollama_port}/api/ps",
    ]
    
    for url in test_urls:
        print(f"\n   Testing: {url}")
        try:
            response = requests.get(url, timeout=5)
            print(f"   ✓ SUCCESS: Status {response.status_code}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   Response keys: {list(data.keys())}")
                except:
                    print(f"   Response: {response.text[:100]}")
        except requests.exceptions.ConnectionError as e:
            print(f"   ✗ CONNECTION ERROR: {str(e)[:100]}")
        except requests.exceptions.Timeout:
            print(f"   ✗ TIMEOUT: Connection timed out")
        except Exception as e:
            print(f"   ✗ ERROR: {type(e).__name__}: {str(e)[:100]}")
    
    # Test 4: Test through OllamaService
    print("\n4. Testing through OllamaService:")
    from app.services.ollama import OllamaService
    service = OllamaService(app)
    
    try:
        api_url = service.get_api_url()
        print(f"   API URL: {api_url}")
        
        response = service._session.get(api_url, timeout=5)
        print(f"   ✓ SUCCESS: Status {response.status_code}")
    except Exception as e:
        print(f"   ✗ ERROR: {type(e).__name__}: {str(e)[:150]}")
    
    # Test 5: Check if port is in use
    print("\n5. Network Check:")
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('localhost', 11434))
        sock.close()
        if result == 0:
            print("   ✓ Port 11434 is open on localhost")
        else:
            print(f"   ✗ Port 11434 is not accessible (error code: {result})")
    except Exception as e:
        print(f"   ✗ Socket test failed: {e}")
    
    print("\n" + "=" * 60)
    print("Diagnostic Complete")
    print("=" * 60)

if __name__ == '__main__':
    test_ollama_connection()

