import sys
sys.path.append('.')

from app.services.ollama import OllamaService

service = OllamaService()
service.app = None  # Test without app

print("Testing get_best_models():")
best = service.get_best_models()
print(f"  Count: {len(best)}")
print(f"  Names: {[m['name'] for m in best]}")

print("\nTesting get_all_downloadable_models():")
all_models = service.get_all_downloadable_models()
print(f"  Count: {len(all_models)}")
print(f"  Names: {[m['name'] for m in all_models]}")

print("\nTesting get_downloadable_models('best'):")
best_via_method = service.get_downloadable_models('best')
print(f"  Count: {len(best_via_method)}")

print("\nTesting get_downloadable_models('all'):")
all_via_method = service.get_downloadable_models('all')
print(f"  Count: {len(all_via_method)}")
print(f"  Names: {[m['name'] for m in all_via_method]}")
