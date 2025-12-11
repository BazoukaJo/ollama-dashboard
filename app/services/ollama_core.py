"""Core functionality for OllamaService.

Handles initialization, background updates, caching, and health monitoring.
"""
# pylint: disable=line-too-long,unnecessary-ellipsis,broad-exception-caught
import os
import atexit
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

import requests

# Note: load_model_settings is used indirectly via OllamaServiceUtilities mixin

if TYPE_CHECKING:
    # Type hints for mixin methods available at runtime
    class OllamaServiceMixinProtocol:
        """Protocol for mixin methods available at runtime."""
        def _get_system_stats_raw(self) -> Dict[str, Any]:
            """Get raw system statistics."""
            ...
        def _format_running_model_entry(self, _: Dict) -> Dict:
            """Format a running model entry."""
            ...
        def _ensure_model_settings_exists(self, _: Dict) -> None:
            """Ensure model settings exist."""
            ...
        def _normalize_available_model_entry(self, _: Dict) -> Dict:
            """Normalize an available model entry."""
            ...
        def load_history(self) -> deque:
            """Load history from disk."""
            ...
        def load_model_settings(self) -> Dict:
            """Load model settings from disk."""
            ...
        def get_service_status(self) -> bool:
            """Check if service is running."""
            ...
        def start_service(self) -> Dict[str, Any]:
            """Start the service."""
            ...
        def _verify_ollama_api(self) -> tuple:
            """Verify Ollama API is accessible."""
            ...
        def save_history(self) -> None:
            """Save history to disk."""
            ...


class OllamaServiceCore:
    """Core functionality for OllamaService including initialization, background updates, and caching."""
    # pylint: disable=no-member

    if TYPE_CHECKING:
        # Declare mixin methods for type checking
        logger: logging.Logger
        _session: requests.Session
        def _get_system_stats_raw(self) -> Dict[str, Any]:
            """Get raw system statistics."""
            ...
        def _format_running_model_entry(self, _: Dict) -> Dict:
            """Format a running model entry."""
            ...
        def _ensure_model_settings_exists(self, _: Dict) -> None:
            """Ensure model settings exist."""
            ...
        def _normalize_available_model_entry(self, _: Dict) -> Dict:
            """Normalize an available model entry."""
            ...
        def load_history(self) -> deque:
            """Load history from disk."""
            ...
        def load_model_settings(self) -> Dict:
            """Load model settings from disk."""
            ...
        def get_service_status(self) -> bool:
            """Check if service is running."""
            ...
        def start_service(self) -> Dict[str, Any]:
            """Start the service."""
            ...
        def _verify_ollama_api(self) -> tuple:
            """Verify Ollama API is accessible."""
            ...
        def save_history(self) -> None:
            """Save history to disk."""
            ...
    def __init__(self, app=None):
        """Initialize OllamaServiceCore with optional Flask app."""
        self.app = app
        self._cache = {}
        self._cache_timestamps = {}
        # Store session in __dict__ directly to avoid property conflicts during init
        self.__dict__['_session'] = requests.Session()
        self._background_stats = None
        self._stats_lock = threading.Lock()
        # Store logger in __dict__ directly to avoid property conflicts during init
        self.logger = logging.getLogger(__name__)
        self._model_settings_lock = threading.Lock()
        self._model_settings = {}
        self._stop_background = threading.Event()
        self._consecutive_ps_failures = 0
        self._last_background_error = None
        self._model_update_counter = 0
        if app is not None:
            self.init_app(app)
        else:
            self.history = deque(maxlen=50)
            self.history = deque(maxlen=50)

    def init_app(self, app):
        """Initialize the OllamaService with a Flask app."""
        self.app = app
        with self.app.app_context():
            # Check if load_history is available (from OllamaServiceUtilities mixin)
            if hasattr(self, 'load_history') and callable(getattr(self, 'load_history', None)):
                try:
                    loaded_history = getattr(self, 'load_history')() or deque(maxlen=50)  # Load history from file (defined in OllamaServiceUtilities)
                    self.history = loaded_history
                except (OSError, IOError) as e:
                    self.logger.warning("Failed to load history: %s", e)
                    self.history = deque(maxlen=50)
            else:
                self.logger.warning("load_history not available, using empty history")
                self.history = deque(maxlen=50)
        self._start_background_updates()
        try:
            # Check if load_model_settings is available (from OllamaServiceUtilities mixin)
            if hasattr(self, 'load_model_settings') and callable(getattr(self, 'load_model_settings', None)):
                self._model_settings = getattr(self, 'load_model_settings')() or {}  # Defined in OllamaServiceUtilities
            else:
                self.logger.warning("load_model_settings not available, using empty settings")
                self._model_settings = {}
        except Exception as e:
            self.logger.exception("Model settings load error: %s", e)
            self._model_settings = {}

        # Auto-start Ollama if enabled and not running
        # Run in a separate thread to avoid blocking app initialization
        auto_start = app.config.get('AUTO_START_OLLAMA', True)
        if auto_start:
            def delayed_auto_start():
                # Small delay to let app fully initialize
                time.sleep(1)
                try:
                    self._auto_start_ollama()
                except Exception as e:
                    self.logger.exception("Error in auto-start thread: %s", e)
            threading.Thread(target=delayed_auto_start, daemon=True, name="AutoStartOllama").start()

        atexit.register(self._cleanup)
    def _start_background_updates(self):
        """Start the background thread for periodic data collection."""
        if self._background_stats and self._background_stats.is_alive():
            return
        self._stop_background.clear()
        self._background_stats = threading.Thread(
            target=self._background_updates_worker,
            daemon=True,
            name="BackgroundDataCollector"
        )
        self._background_stats.start()

    def _auto_start_ollama(self):
        """Attempt to auto-start Ollama service if not running."""
        try:
            # Safely check service status
            try:
                # Check if get_service_status is available (from OllamaServiceControl mixin)
                if hasattr(self, 'get_service_status') and callable(getattr(self, 'get_service_status', None)):
                    is_running = getattr(self, 'get_service_status')() or False  # Defined in OllamaServiceControl
                else:
                    self.logger.warning("get_service_status not available, assuming not running")
                    is_running = False
            except Exception as e:
                self.logger.warning("Could not check Ollama service status: %s. Attempting auto-start anyway.", e)
                is_running = False

            if is_running:
                self.logger.info("Ollama service already running, skipping auto-start")
                return

            self.logger.info("Ollama service not running, attempting auto-start...")
            try:
                # Check if start_service is available (from OllamaServiceControl mixin)
                if hasattr(self, 'start_service') and callable(getattr(self, 'start_service', None)):
                    result = getattr(self, 'start_service')() or {}  # Defined in OllamaServiceControl
                else:
                    self.logger.warning("start_service not available, cannot auto-start")
                    return
            except Exception as e:

                self.logger.warning("Error calling start_service during auto-start: %s", e)
                return

            if result and result.get("success"):
                self.logger.info("Ollama auto-start successful: %s", result.get('message', ''))
                # Verify API is accessible with a short delay
                time.sleep(2)
                try:
                    # Check if _verify_ollama_api is available (from OllamaServiceControl mixin)
                    if hasattr(self, '_verify_ollama_api') and callable(getattr(self, '_verify_ollama_api', None)):
                        verify_result = getattr(self, '_verify_ollama_api')() or (False, "No result")  # Defined in OllamaServiceControl
                        if isinstance(verify_result, tuple) and len(verify_result) >= 2:
                            api_ok, api_msg = verify_result[0], verify_result[1]
                            if api_ok:
                                self.logger.info("Ollama API is accessible after auto-start: %s", api_msg)
                            else:
                                self.logger.warning("Ollama started but API verification failed: %s", api_msg)
                        else:
                            self.logger.warning("_verify_ollama_api returned unexpected result format: %s", type(verify_result))
                    else:
                        self.logger.warning("_verify_ollama_api not available, skipping verification")
                except Exception as e:
                    self.logger.warning("Ollama started but API verification error: %s", e)
            else:
                error_msg = result.get('message', 'Unknown error') if result else 'No result returned'
                self.logger.warning("Ollama auto-start failed: %s", error_msg)
        except Exception as e:
            # Don't fail app initialization if auto-start fails
            self.logger.exception("Error during Ollama auto-start (non-fatal): %s", e)

    def _background_updates_worker(self):
        """Periodically collect system stats, running models, available models, and version info."""
        while not self._stop_background.is_set():
            try:
                cycle_had_ps_failure = False
                # Check if _get_system_stats_raw is available (from OllamaServiceModels mixin)
                if hasattr(self, '_get_system_stats_raw') and callable(getattr(self, '_get_system_stats_raw', None)):
                    stats = getattr(self, '_get_system_stats_raw')() or {}  # Defined in OllamaServiceModels
                else:
                    self.logger.warning("_get_system_stats_raw not available, skipping system stats update")
                    stats = {}
                with self._stats_lock:
                    self._cache['system_stats'] = stats
                    self._cache_timestamps['system_stats'] = datetime.now()
                self._model_update_counter += 1
                if self._model_update_counter >= 1:  # Refresh running models every cycle for faster visibility
                    try:
                        host, port = self._get_ollama_host_port()
                        ps_url = f"http://{host}:{port}/api/ps"
                        response = self._session.get(ps_url, timeout=5)
                        if response.status_code == 200:
                            data = response.json()
                            models = data.get('models', [])
                            current_models = [self._format_running_model_entry(m) for m in models]  # In OllamaServiceModels
                            for m in current_models:
                                try:
                                    self._ensure_model_settings_exists(m)  # In OllamaServiceUtilities
                                except Exception:
                                    pass
                            with self._stats_lock:
                                self._cache['running_models'] = current_models
                                self._cache_timestamps['running_models'] = datetime.now()
                            self._consecutive_ps_failures = 0
                            # Clear error on successful connection
                            if self._last_background_error:
                                self._last_background_error = None
                        else:
                            cycle_had_ps_failure = True
                            self._last_background_error = f"ps status {response.status_code}"
                    except Exception as e:
                        cycle_had_ps_failure = True
                        self.logger.exception("Background model collection error: %s", e)
                        # Store user-friendly error message
                        self._last_background_error = self._sanitize_error_message(e)
                    if self._model_update_counter >= 15:
                        try:
                            host, port = self._get_ollama_host_port()
                            tags_url = f"http://{host}:{port}/api/tags"
                            response = self._session.get(tags_url, timeout=10)
                            if response.status_code == 200:
                                models = response.json().get('models', [])
                                models = [self._normalize_available_model_entry(m) for m in models]  # In OllamaServiceModels
                                with self._stats_lock:
                                    self._cache['available_models'] = models
                                    self._cache_timestamps['available_models'] = datetime.now()
                            else:
                                self._last_background_error = f"tags status {response.status_code}"
                        except Exception as e:
                            self.logger.exception("Background available models collection error: %s", e)
                            self._last_background_error = self._sanitize_error_message(e)
                        try:
                            version_url = f"http://{host}:{port}/api/version"
                            response = self._session.get(version_url, timeout=5)
                            if response.status_code == 200:
                                data = response.json()
                                version = data.get('version', 'Unknown')
                                with self._stats_lock:
                                    self._cache['ollama_version'] = version
                                    self._cache_timestamps['ollama_version'] = datetime.now()
                            else:
                                self._last_background_error = f"version status {response.status_code}"
                        except Exception as e:
                            self.logger.exception("Background version collection error: %s", e)
                            self._last_background_error = self._sanitize_error_message(e)
                        self._model_update_counter = 0
                if cycle_had_ps_failure:
                    self._consecutive_ps_failures += 1
                else:
                    self._consecutive_ps_failures = 0
            except Exception as e:
                self.logger.exception("Background updates error: %s", e)
                self._last_background_error = self._sanitize_error_message(e)
            base_interval = 2
            backoff_multiplier = 2 ** min(4, self._consecutive_ps_failures) if self._consecutive_ps_failures > 0 else 1
            sleep_seconds = base_interval * backoff_multiplier
            self._stop_background.wait(sleep_seconds)

    # Simple cache helpers restored after refactor corruption
    def _get_cached(self, key, ttl_seconds):
        """Get a cached value if it exists and hasn't expired."""
        ts = self._cache_timestamps.get(key)
        if not ts:
            return None
        if (datetime.now() - ts).total_seconds() < ttl_seconds:
            return self._cache.get(key)
        return None

    def _set_cached(self, key, value):
        """Cache a value with current timestamp."""
        self._cache[key] = value
        self._cache_timestamps[key] = datetime.now()

    def _get_ollama_host_port(self):
        """Get Ollama host and port with proper fallbacks."""
        logger = self.__dict__.get('logger', logging.getLogger(__name__))
        try:
            if self.app:
                host = self.app.config.get('OLLAMA_HOST')
                port = self.app.config.get('OLLAMA_PORT')
                # Fallback to environment variables if config values are None or empty
                if not host:
                    host = os.getenv('OLLAMA_HOST', 'localhost')
                if not port:
                    try:
                        port = int(os.getenv('OLLAMA_PORT', '11434'))
                    except (ValueError, TypeError):
                        port = 11434
            else:
                host = os.getenv('OLLAMA_HOST', 'localhost')
                try:
                    port = int(os.getenv('OLLAMA_PORT', '11434'))
                except (ValueError, TypeError):
                    port = 11434

            # Ensure we have valid values
            if not host or not isinstance(host, str):
                host = 'localhost'
            if not port:
                port = 11434

            # Convert port to int if it's a string
            try:
                port = int(port)
            except (ValueError, TypeError):
                port = 11434

            # Validate port range
            if not 1 <= port <= 65535:
                logger.warning("Invalid port %s, using default 11434", port)
                port = 11434

            return host, port
        except Exception as e:
            logger.warning("Error getting host/port, using defaults: %s", e)
            return 'localhost', 11434

    # Public-facing alias used by tests and mixins
    def get_ollama_host_port(self):
        """Return Ollama host/port (compat shim for mixin calls)."""
        return self._get_ollama_host_port()

    def _sanitize_error_message(self, error):
        """Convert technical error messages to user-friendly ones."""
        if not error:
            return None
        error_str = str(error).lower()
        # Check for various connection error patterns
        connection_indicators = [
            'connection', 'refused', '10061', 'max retries', 'httpconnectionpool',
            'newconnectionerror', 'failed to establish', 'target machine actively refused',
            'no connection could be made', '/api/ps'
        ]
        if any(indicator in error_str for indicator in connection_indicators):
            return "Cannot connect to Ollama server. Please ensure Ollama is running on localhost:11434."
        return str(error)

    def get_component_health(self):
        """Return health/status information for background thread and caches."""
        now = datetime.now()
        age_info = {}
        stale = {}
        ttl_map = {
            'system_stats': 5,
            'running_models': 3,
            'available_models': 60,
            'ollama_version': 300
        }
        for key, ttl in ttl_map.items():
            ts = self._cache_timestamps.get(key)
            if ts:
                age = (now - ts).total_seconds()
            else:
                age = None
            age_info[key] = age
            stale[key] = (age is None) or (age > ttl)

        # Health status logic
        thread_alive = bool(self._background_stats and self._background_stats.is_alive())
        running_models = self._cache.get('running_models', [])
        available_models = self._cache.get('available_models', [])
        degraded = not thread_alive or self._consecutive_ps_failures > 0 or stale.get('system_stats', True)
        unhealthy = self._last_background_error is not None or not thread_alive
        status = 'healthy'
        if unhealthy:
            status = 'unhealthy'
        elif degraded:
            status = 'degraded'

        # Sanitize error message for user-friendly display (errors are already sanitized when stored, but double-check)
        error_message = self._sanitize_error_message(self._last_background_error) if self._last_background_error else None

        uptime_seconds = 0
        if self.app:
            start_time = self.app.config.get('START_TIME')
            now_utc = datetime.now(timezone.utc)
            if start_time is None:
                start_time = now_utc
            elif start_time.tzinfo:
                start_time = start_time.astimezone(timezone.utc)
            else:
                start_time = start_time.replace(tzinfo=timezone.utc)
            uptime_seconds = int((now_utc - start_time).total_seconds())

        return {
            'status': status,
            'background_thread_alive': thread_alive,
            'consecutive_ps_failures': self._consecutive_ps_failures,
            'last_background_error': self._last_background_error,  # Keep raw for debugging
            'cache_age_seconds': age_info,
            'stale_flags': stale,
            'models': {
                'running_count': len(running_models),
                'available_count': len(available_models)
            },
            'uptime_seconds': uptime_seconds,
            'error': error_message  # User-friendly error message
        }

    def clear_all_caches(self):
        """Clear all cached data and timestamps (used after service restart)."""
        self._cache.clear()
        self._cache_timestamps.clear()
        # Also reset error states
        self._last_background_error = None
        self._consecutive_ps_failures = 0

    def clear_cache(self, key):
        """Clear a specific cache entry and its timestamp."""
        if key in self._cache:
            del self._cache[key]
        if key in self._cache_timestamps:
            del self._cache_timestamps[key]

    def _cleanup(self):
        """Cleanup resources on process exit."""
        try:
            if hasattr(self, '_stop_background') and self._stop_background:
                self._stop_background.set()
            if hasattr(self, '_background_stats') and self._background_stats and self._background_stats.is_alive():
                self._background_stats.join(timeout=2)
        except Exception:
            pass
        try:
            self.save_history()  # Defined in OllamaServiceUtilities
        except Exception:
            pass
