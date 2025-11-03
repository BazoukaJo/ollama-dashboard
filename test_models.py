from app.services.ollama import OllamaService

# Test the Ollama service
s = OllamaService()
print('Available models:', len(s.get_available_models()))
print('Running models:', len(s.get_running_models()))

# Print some model details
available = s.get_available_models()
if available:
    print('First available model:', available[0]['name'])

running = s.get_running_models()
if running:
    print('First running model:', running[0]['name'])
else:
    print('No running models')
