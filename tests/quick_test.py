import requests
r = requests.get('http://127.0.0.1:5000/api/models/available', timeout=5)
data = r.json()
models = data.get('models', [])
print(f'Total models: {len(models)}')
for m in models:
    print(f"  {m['name']}: has_vision={m.get('has_vision')}, has_tools={m.get('has_tools')}, has_reasoning={m.get('has_reasoning')}")
