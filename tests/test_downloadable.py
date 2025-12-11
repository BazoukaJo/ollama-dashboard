import traceback
from app import create_app
from app.routes.main import ollama_service

app = create_app()
ollama_service.init_app(app)

with app.app_context():
    try:
        models = ollama_service.get_downloadable_models('best')
        print(f"Success! Got {len(models)} models")
        print(f"First model: {models[0]}")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
