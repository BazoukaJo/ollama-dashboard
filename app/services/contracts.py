"""Service interface contracts (ABCs) for Ollama Dashboard.

Defines formal interfaces that all service classes must implement.
This ensures type safety and clear responsibilities across mixins.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from collections import deque


class ICacheProvider(ABC):
    """Contract for cache operations."""

    @abstractmethod
    def _get_cached(self, key: str, ttl_seconds: int = 30) -> Optional[Any]:
        """Get cached value if not expired."""
        pass

    @abstractmethod
    def _set_cached(self, key: str, value: Any) -> None:
        """Store value in cache."""
        pass

    @abstractmethod
    def _get_cache_age(self, key: str) -> float:
        """Get age of cache entry in seconds (-1 if missing)."""
        pass


class IModelService(ABC):
    """Contract for model operations."""

    @abstractmethod
    def get_running_models(self) -> List[Dict]:
        """Get list of running models."""
        pass

    @abstractmethod
    def get_available_models(self) -> List[Dict]:
        """Get list of available models."""
        pass

    @abstractmethod
    def get_model_info_cached(self, model_name: str) -> Optional[Dict]:
        """Get cached model info."""
        pass

    @abstractmethod
    def start_model(self, model_name: str) -> Dict:
        """Start a model with retry logic."""
        pass

    @abstractmethod
    def stop_model(self, model_name: str) -> Dict:
        """Stop a running model."""
        pass

    @abstractmethod
    def delete_model(self, model_name: str) -> Dict:
        """Delete a model."""
        pass


class IServiceControl(ABC):
    """Contract for service control operations."""

    @abstractmethod
    def get_service_status(self) -> bool:
        """Check if Ollama service is running."""
        pass

    @abstractmethod
    def start_service(self) -> Dict[str, Any]:
        """Start Ollama service."""
        pass

    @abstractmethod
    def stop_service(self) -> Dict[str, Any]:
        """Stop Ollama service."""
        pass

    @abstractmethod
    def restart_service(self) -> Dict[str, Any]:
        """Restart Ollama service."""
        pass


class IObservable(ABC):
    """Contract for observability operations."""

    @abstractmethod
    def get_component_health(self) -> Dict[str, Any]:
        """Get health status of all components."""
        pass

    @abstractmethod
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        pass

    @abstractmethod
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        pass

    @abstractmethod
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system resource statistics."""
        pass


class IPersistent(ABC):
    """Contract for persistence operations."""

    @abstractmethod
    def load_history(self) -> deque:
        """Load conversation history from disk."""
        pass

    @abstractmethod
    def save_history(self) -> None:
        """Save conversation history to disk."""
        pass

    @abstractmethod
    def load_model_settings(self) -> Dict:
        """Load model settings from disk."""
        pass

    @abstractmethod
    def save_model_settings(self, model_name: str, settings: Dict) -> bool:
        """Save settings for a specific model."""
        pass


class IOllamaService(ICacheProvider, IModelService, IServiceControl, IObservable, IPersistent):
    """Complete contract for OllamaService - combines all interfaces."""
    pass
