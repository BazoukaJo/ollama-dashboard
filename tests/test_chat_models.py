import requests
import json

# Test the chat models API endpoint
try:
    response = requests.get('http://localhost:5000/api/models/available', timeout=5)
    print(f'Status Code: {response.status_code}')
    if response.status_code == 200:
        data = response.json()
        print('API Response:')
        print(json.dumps(data, indent=2))
        print(f'Number of models: {len(data.get("models", []))}')
        if data.get("models"):
            print(f'First model: {data["models"][0]["name"]}')
    else:
        print(f'Error: {response.text}')
except requests.exceptions.ConnectionError:
    print('Connection Error: Flask app is not running on localhost:5000')
except (requests.RequestException, OSError) as e:
    print(f'Error: {e}')
