"""Global OllamaService instance."""

from app.services.ollama import OllamaService

# Create singleton instance
ollama_service = OllamaService()
