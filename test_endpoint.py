from app import create_app

app = create_app()

with app.test_client() as client:
    # Test the downloadable endpoint
    response = client.get('/api/models/downloadable?category=best')
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.get_json()
        print(f"Models: {len(data.get('models', []))}")
        print(f"First model: {data['models'][0]['name']}")
    else:
        print(f"Error: {response.get_data(as_text=True)}")
