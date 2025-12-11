"""Model management functionality for OllamaService: model operations, info retrieval, and capabilities."""

from typing import Any, Protocol, Tuple

import requests
from app.services.system_stats import get_vram_info
from app.services.system_stats import get_disk_info
from app.services.capabilities import detect_capabilities
from app.services.capabilities import ensure_capability_flags
from app.services.model_helpers import (format_running_model_entry,
                                        normalize_available_model_entry)
from app.services.system_stats import collect_system_stats, models_memory_usage


class OllamaConnectionError(Exception):
    """Exception raised when connection to Ollama server fails."""


class OllamaServiceCoreProtocol(Protocol):
    """Protocol for OllamaService core functionality."""
    _session: requests.Session
    logger: Any
    _model_settings_lock: Any  # type: ignore[attr-defined]

    def get_ollama_host_port(self) -> Tuple[str, int]:
        """Get Ollama host and port."""
        raise NotImplementedError("Subclass must implement get_ollama_host_port()")

    def update_history(self, models: list) -> None:
        """Update model history."""

    def load_model_settings(self) -> dict:
        """Load model settings from disk."""
        return {}


class OllamaServiceModels:
    """Mixin supplying model-related helpers used by OllamaService."""

    # pylint: disable=no-member

    def _get_cached(self, key, ttl_seconds=None):
        """Get a cached value by key with optional TTL check."""
        raise NotImplementedError("_get_cached must be implemented by the base class.")

    def _set_cached(self, key, value):
        """Cache a value with an optional timestamp."""
        raise NotImplementedError("_set_cached must be implemented by the base class.")

    @property
    def _ollama_core(self) -> OllamaServiceCoreProtocol:
        """Return self as OllamaServiceCoreProtocol for duck typing."""
        return self  # type: ignore[attr-defined]

    @property
    def _session(self) -> requests.Session:
        """Get the requests session for HTTP calls."""
        # Access directly from instance dict to avoid recursion
        session = self.__dict__.get('_session')
        if session is None:
            raise AttributeError("_session not initialized")
        return session

    @_session.setter
    def _session(self, value: requests.Session):
        """Set the requests session."""
        self.__dict__['_session'] = value

    @property
    def logger(self) -> Any:
        """Get the logger instance."""
        return self.__dict__.get('logger')

    @logger.setter
    def logger(self, value: Any):
        """Set the logger instance."""
        self.__dict__['logger'] = value

    def _normalize_available_model_entry(self, entry):
        """Normalize a model entry from the available models list."""
        return normalize_available_model_entry(self, entry)

    def _format_running_model_entry(self, model, **kwargs):
        """Format a running model entry."""
        return format_running_model_entry(self, model, **kwargs)

    def get_api_url(self):
        """Get the base Ollama API URL for process list endpoint."""
        if not hasattr(self._ollama_core, 'get_ollama_host_port'):
            raise AttributeError(
                "OllamaServiceModels requires a base class that implements 'get_ollama_host_port'."
            )
        try:
            host, port = self._ollama_core.get_ollama_host_port()
            return f"http://{host}:{port}/api/ps"
        except Exception as exc:
            raise ConnectionError(
                f"Failed to connect to Ollama server: {exc}. Ensure Ollama is running and accessible."
            ) from exc

    def get_ollama_version(self):
        """Get the Ollama server version."""
        cached = self._get_cached('ollama_version', ttl_seconds=300)
        if cached is not None:
            return cached
        try:
            host, port = self._ollama_core.get_ollama_host_port()
            url = f"http://{host}:{port}/api/version"
            response = self._session.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            version = data.get('version', 'Unknown')
            self._set_cached('ollama_version', version)
            return version
        except Exception:
            return 'Unknown'

    def get_system_stats(self):
        """Get system statistics with defensive normalization."""
        cached = self._get_cached('system_stats', ttl_seconds=5)
        if cached is not None:
            stats = cached
        else:
            stats = collect_system_stats()
            self._set_cached('system_stats', stats)

        # Normalize vram
        if 'vram' not in stats or not isinstance(stats['vram'], dict):
            stats['vram'] = {'total': 0, 'used': 0, 'free': 0, 'percent': 0}
        else:
            for key in ['total', 'used', 'free', 'percent']:
                if key not in stats['vram'] or stats['vram'][key] is None:
                    stats['vram'][key] = 0

        # Normalize memory
        if 'memory' not in stats or not isinstance(stats['memory'], dict):
            stats['memory'] = {'percent': 0, 'total': 0, 'available': 0, 'used': 0}
        else:
            for key in ['percent', 'total', 'available', 'used']:
                if key not in stats['memory'] or stats['memory'][key] is None:
                    stats['memory'][key] = 0

        # Normalize disk
        if 'disk' not in stats or not isinstance(stats['disk'], dict):
            stats['disk'] = {'percent': 0, 'total': 0, 'used': 0, 'free': 0}
        else:
            for key in ['percent', 'total', 'used', 'free']:
                if key not in stats['disk'] or stats['disk'][key] is None:
                    stats['disk'][key] = 0

        return stats

    def _get_system_stats_raw(self):
        """Get raw system statistics without normalization."""
        return collect_system_stats()

    def _get_vram_info(self):
        """Get GPU VRAM information."""
        return get_vram_info()

    def _get_disk_info(self):
        """Get disk usage information."""
        return get_disk_info()

    def _detect_model_capabilities(self, model):
        """Detect model capabilities like vision, tools, and reasoning."""
        model_name = model.get('name', '') if isinstance(model, dict) else ''
        details = model.get('details', {}) or {}
        families = details.get('families', []) or []
        return detect_capabilities(model_name, families)

    def _ensure_capability_flags(self, model):
        """Ensure all required capability flags are present in a model."""
        return ensure_capability_flags(model)

    def get_detailed_model_info(self, model_name):
        """Get detailed model information including capabilities."""
        try:
            response = self._session.post(
                self.get_api_url().replace('/api/ps', '/api/show'),
                json={"name": model_name},
                timeout=10,
            )
            if response.status_code != 200:
                return None
            data = response.json()
            capabilities = self._detect_model_capabilities({
                'name': model_name,
                'details': data.get('details', {})
            })
            return {
                **data,
                **capabilities,
            }
        except Exception as exc:
            self.logger.debug("Detailed info fetch failed for %s: %s", model_name, exc)
            return None

    def get_available_models(self):
        """Get list of available models from the Ollama server."""
        # Always fetch fresh to avoid stale capability flags and to honor test monkeypatching
        try:
            host, port = self._ollama_core.get_ollama_host_port()
            tags_url = f"http://{host}:{port}/api/tags"
            response = self._session.get(tags_url, timeout=10)
            response.raise_for_status()
            raw_json = response.json()
            models = raw_json.get('models', []) if isinstance(raw_json, dict) else []
            normalized = [self._normalize_available_model_entry(m) for m in models]
            if not normalized:
                try:
                    curated = self.get_all_downloadable_models()
                    normalized = [self._normalize_available_model_entry(entry) for entry in curated]
                except Exception:
                    normalized = []
            self._set_cached('available_models', normalized)
            return normalized
        except Exception as exc:
            self.logger.debug("Error fetching available models: %s", exc)
            return []

    def get_running_models(self):
        """Get list of currently running models."""
        cached = self._get_cached('running_models', ttl_seconds=3)
        if cached is not None:
            return cached
        try:
            response = self._session.get(self.get_api_url(), timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data.get('models', [])
            current_models = [self._format_running_model_entry(m) for m in models]
            self._set_cached('running_models', current_models)
            return current_models
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError(
                "Could not connect to Ollama server. Please ensure it's running and accessible."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaConnectionError(
                "Connection to Ollama server timed out. Please check your network connection."
            ) from exc
        except Exception as exc:
            raise OllamaConnectionError(f"Error fetching models: {exc}") from exc

    def get_model_info_cached(self, model_name):
        """Get cached model info from running or available models."""
        try:
            running_models = self.get_running_models()
            for model in running_models:
                if model.get('name') == model_name:
                    return model
            available_models = self.get_available_models()
            for model in available_models:
                if model.get('name') == model_name:
                    return model
            return None
        except Exception as exc:
            self.logger.exception("Error getting model info_cached for %s: %s", model_name, exc)
            return None

    def _has_custom_settings(self, model_name):
        """Check if a model has custom settings (user-defined)."""
        try:
            # pylint: disable=protected-access
            with self._ollama_core._model_settings_lock:
                model_settings = getattr(self, '_model_settings', None)
                if not model_settings:
                    model_settings = self._ollama_core.load_model_settings() or {}
                    setattr(self, '_model_settings', model_settings)
                entry = model_settings.get(model_name)
                return bool(entry) and entry.get('source') == 'user'
        except Exception:
            return False

    def has_custom_model_settings(self, model_name):
        """Public method to check if a model has custom settings (user-defined)."""
        return self._has_custom_settings(model_name)

    def get_models_memory_usage(self):
        """Get memory usage information for running models."""
        try:
            running_models = self.get_running_models()
            return models_memory_usage(running_models)
        except Exception as exc:
            self.logger.exception("Error getting models memory usage: %s", exc)
            return {
                'system_ram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
                'system_vram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
                'models': [],
                'error': str(exc),
            }
