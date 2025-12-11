"""Main OllamaService class that composes functionality from modular components."""

import requests  # Exposed for test monkeypatching of Session methods

from app.services.ollama_core import OllamaServiceCore
from app.services.ollama_models import OllamaServiceModels
from app.services.ollama_service_control import OllamaServiceControl
from app.services.ollama_utilities import OllamaServiceUtilities


class OllamaService(
    OllamaServiceCore,
    OllamaServiceModels,
    OllamaServiceControl,
    OllamaServiceUtilities
):
    """Service class for managing Ollama API interactions and operations.

    Provides functionality for:
    - Model management (running, available, downloadable models)
    - System statistics collection and caching
    - Service control (start, stop, restart Ollama service)
    - Model settings management
    - Background data collection and caching
    - Chat history and session management
    """
