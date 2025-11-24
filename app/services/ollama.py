from flask import current_app
import logging
import re  # kept for other helpers; capability detection moved to capabilities.py
import requests
from datetime import datetime, timezone, timedelta
import time
import json
import os
from collections import deque
import psutil
import platform
from app.services.model_settings_helpers import (
    model_settings_file_path,
    load_model_settings,
    write_model_settings_file,
    get_model_settings_entry,
    get_model_settings_with_fallback_entry,
    save_model_settings_entry,
    delete_model_settings_entry,
    ensure_model_settings_exists,
    recommend_settings_for_model,
    normalize_setting_value,
)
from app.services.service_control import stop_service_windows, stop_service_unix
import threading
import atexit
from app.services.system_stats import models_memory_usage

class OllamaService:
    def __init__(self, app=None):
        self.app = app
        self._cache = {}
        self._cache_timestamps = {}
        self._session = requests.Session()
        self._background_stats = None
        self._stats_lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        self._model_settings_lock = threading.Lock()
        self._model_settings = {}
        self._stop_background = threading.Event()
        self._consecutive_ps_failures = 0
        self._last_background_error = None
        if app is not None:
            self.init_app(app)
        else:
            self.history = deque(maxlen=50)

    def init_app(self, app):
        self.app = app
        with self.app.app_context():
            self.history = self.load_history()  # Load history from file
        self._start_background_updates()
        try:
            self._model_settings = self.load_model_settings()
        except Exception as e:
            self.logger.exception("Model settings load error: %s", e)  # Log model settings load error
        atexit.register(self._cleanup)

    def _start_background_updates(self):
        if self._background_stats and self._background_stats.is_alive():
            return
        self._stop_background.clear()
        self._background_stats = threading.Thread(
            target=self._background_updates_worker,
            daemon=True,
            name="BackgroundDataCollector"
        )
        self._background_stats.start()

    def _background_updates_worker(self):
        while not self._stop_background.is_set():
            try:
                cycle_had_ps_failure = False
                stats = self._get_system_stats_raw()
                with self._stats_lock:
                    self._cache['system_stats'] = stats
                    self._cache_timestamps['system_stats'] = datetime.now()
                if not hasattr(self, '_model_update_counter'):
                    self._model_update_counter = 0
                self._model_update_counter += 1
                if self._model_update_counter >= 5:  # Check if model update counter exceeds threshold
                    try:
                        response = self._session.get(self.get_api_url(), timeout=5)
                        if response.status_code == 200:
                            data = response.json()
                            models = data.get('models', [])
                            current_models = [self._format_running_model_entry(m) for m in models]
                            for m in current_models:
                                try:
                                    self._ensure_model_settings_exists(m)
                                except Exception:
                                    pass
                            with self._stats_lock:
                                self._cache['running_models'] = current_models
                                self._cache_timestamps['running_models'] = datetime.now()
                            self._consecutive_ps_failures = 0
                        else:
                            cycle_had_ps_failure = True
                            self._last_background_error = f"ps status {response.status_code}"
                    except Exception as e:
                        cycle_had_ps_failure = True
                        self.logger.exception("Background model collection error: %s", e)
                        self._last_background_error = str(e)
                    if self._model_update_counter >= 15:
                        try:
                            if self.app:
                                host = self.app.config.get('OLLAMA_HOST')
                                port = self.app.config.get('OLLAMA_PORT')
                            else:
                                host = os.getenv('OLLAMA_HOST', 'localhost')
                                port = int(os.getenv('OLLAMA_PORT', '11434'))
                            tags_url = f"http://{host}:{port}/api/tags"
                            response = self._session.get(tags_url, timeout=10)
                            if response.status_code == 200:
                                models = response.json().get('models', [])
                                models = [self._normalize_available_model_entry(m) for m in models]
                                with self._stats_lock:
                                    self._cache['available_models'] = models
                                    self._cache_timestamps['available_models'] = datetime.now()
                            else:
                                self._last_background_error = f"tags status {response.status_code}"
                        except Exception as e:
                            self.logger.exception("Background available models collection error: %s", e)
                            self._last_background_error = str(e)
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
                            self._last_background_error = str(e)
                        self._model_update_counter = 0
                if cycle_had_ps_failure:
                    self._consecutive_ps_failures += 1
                else:
                    self._consecutive_ps_failures = 0
            except Exception as e:
                self.logger.exception("Background updates error: %s", e)
                self._last_background_error = str(e)
            base_interval = 2
            backoff_multiplier = 2 ** min(4, self._consecutive_ps_failures) if self._consecutive_ps_failures > 0 else 1
            sleep_seconds = base_interval * backoff_multiplier
            self._stop_background.wait(sleep_seconds)

    # Simple cache helpers restored after refactor corruption
    def _get_cached(self, key, ttl_seconds):
        ts = self._cache_timestamps.get(key)
        if not ts:
            return None
        if (datetime.now() - ts).total_seconds() < ttl_seconds:
            return self._cache.get(key)
        return None

    def _set_cached(self, key, value):
        self._cache[key] = value
        self._cache_timestamps[key] = datetime.now()

    def get_component_health(self):
        """Return health/status information for background thread and caches."""
        now = datetime.now()
        age_info = {}
        stale = {}
        ttl_map = {
            'system_stats': 5,
            'running_models': 10,
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
        return {
            'status': status,
            'background_thread_alive': thread_alive,
            'consecutive_ps_failures': self._consecutive_ps_failures,
            'last_background_error': self._last_background_error,
            'cache_age_seconds': age_info,
            'stale_flags': stale,
            'models': {
                'running_count': len(running_models),
                'available_count': len(available_models)
            },
            'uptime_seconds': int((datetime.now() - self.app.config.get('START_TIME', datetime.now())).total_seconds()) if self.app else 0,
            'error': self._last_background_error
        }

    def clear_all_caches(self):
        """Clear all cached data and timestamps (used after service restart)."""
        self._cache.clear()
        self._cache_timestamps.clear()

    def _normalize_available_model_entry(self, entry):
        from app.services.model_helpers import normalize_available_model_entry
        return normalize_available_model_entry(self, entry)

    def _format_running_model_entry(self, model, include_has_custom_settings=False):
        from app.services.model_helpers import format_running_model_entry
        return format_running_model_entry(self, model, include_has_custom_settings)

    def get_api_url(self):
        try:
            if self.app:
                host = self.app.config.get('OLLAMA_HOST')
                port = self.app.config.get('OLLAMA_PORT')
            else:
                host = os.getenv('OLLAMA_HOST', 'localhost')
                port = int(os.getenv('OLLAMA_PORT', '11434'))
            if not host or not port:
                raise ValueError(f"Missing configuration: OLLAMA_HOST={host}, OLLAMA_PORT={port}")
            return f"http://{host}:{port}/api/ps"
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Ollama server: {str(e)}. Please ensure Ollama is running and accessible.") from e

    def format_size(self, size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

    def format_relative_time(self, target_dt):
        now = datetime.now(timezone.utc)
        diff = target_dt - now
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        if days > 0:
            if hours > 12:
                days += 1
            return f"about {days} {'day' if days == 1 else 'days'}"
        elif hours > 0:
            if minutes > 30:
                hours += 1
            return f"about {hours} {'hour' if hours == 1 else 'hours'}"
        elif minutes > 0:
            if minutes < 5:
                return "a few minutes"
            elif minutes < 15:
                return "about 10 minutes"
            elif minutes < 25:
                return "about 20 minutes"
            elif minutes < 45:
                return "about 30 minutes"
            else:
                return "about an hour"
        else:
            return "less than a minute"

    def get_ollama_version(self):
        cached = self._get_cached('ollama_version', ttl_seconds=300)
        if cached is not None:
            return cached
        try:
            if self.app:
                host = self.app.config.get('OLLAMA_HOST')
                port = self.app.config.get('OLLAMA_PORT')
            else:
                host = os.getenv('OLLAMA_HOST', 'localhost')
                port = int(os.getenv('OLLAMA_PORT', '11434'))
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
        cached = self._get_cached('system_stats', ttl_seconds=5)
        if cached is not None:
            stats = cached
        else:
            from app.services.system_stats import collect_system_stats
            stats = collect_system_stats()
            self._set_cached('system_stats', stats)
        # Ensure vram dict is complete and always present
        if 'vram' not in stats or not isinstance(stats['vram'], dict):
            stats['vram'] = {'total': 0, 'used': 0, 'free': 0, 'percent': 0}
        else:
            for k in ['total', 'used', 'free', 'percent']:
                if k not in stats['vram'] or stats['vram'][k] is None:
                    stats['vram'][k] = 0
        # Defensive: ensure stats['memory'] and stats['disk'] are also dicts with expected keys
        if 'memory' not in stats or not isinstance(stats['memory'], dict):
            stats['memory'] = {'percent': 0, 'total': 0, 'available': 0, 'used': 0}
        else:
            for k in ['percent', 'total', 'available', 'used']:
                if k not in stats['memory'] or stats['memory'][k] is None:
                    stats['memory'][k] = 0
        if 'disk' not in stats or not isinstance(stats['disk'], dict):
            stats['disk'] = {'percent': 0, 'total': 0, 'used': 0, 'free': 0}
        else:
            for k in ['percent', 'total', 'used', 'free']:
                if k not in stats['disk'] or stats['disk'][k] is None:
                    stats['disk'][k] = 0
        return stats

    def _get_system_stats_raw(self):
        from app.services.system_stats import collect_system_stats
        return collect_system_stats()

    def _get_vram_info(self):
        from app.services.system_stats import get_vram_info
        return get_vram_info()

    def _get_disk_info(self):
        from app.services.system_stats import get_disk_info
        return get_disk_info()

    def _detect_model_capabilities(self, model):
        """Delegate capability detection to capabilities helper module."""
        from app.services.capabilities import detect_capabilities
        model_name = model.get('name', '')
        details = model.get('details', {}) or {}
        families = details.get('families', []) or []
        return detect_capabilities(model_name, families)

    def _ensure_capability_flags(self, model):
        """Delegate normalization to helper to keep logic centralized."""
        from app.services.capabilities import ensure_capability_flags
        return ensure_capability_flags(model)

    def get_detailed_model_info(self, model_name):
        """Get detailed model information including capabilities for better detection."""
        try:
            response = self._session.post(
                self.get_api_url().replace('/api/ps', '/api/show'),
                json={"name": model_name},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                # Add capabilities detection based on detailed info
                capabilities = self._detect_model_capabilities({'name': model_name, 'details': data.get('details', {})})
                data['capabilities'] = capabilities

                return data
            return None
        except Exception as e:
            self.logger.debug("Failed to get detailed info for %s: %s", model_name, e)
            return None

    def get_available_models(self):
        """Get list of available models (not just running ones). Ensures capability flags are booleans."""
        cached = self._get_cached('available_models', ttl_seconds=60)  # 1 minute
        # Treat empty list as stale/miss to allow tests to patch responses
        if cached:
            return [self._normalize_available_model_entry(m) for m in cached]
        try:
            if self.app:
                host = self.app.config.get('OLLAMA_HOST')
                port = self.app.config.get('OLLAMA_PORT')
            else:
                host = os.getenv('OLLAMA_HOST', 'localhost')
                port = int(os.getenv('OLLAMA_PORT', '11434'))
            tags_url = f"http://{host}:{port}/api/tags"
            response = self._session.get(tags_url, timeout=10)
            response.raise_for_status()
            raw_json = response.json()
            models = raw_json.get('models', []) if isinstance(raw_json, dict) else []
            normalized = [self._normalize_available_model_entry(m) for m in models]
            self._set_cached('available_models', normalized)
            return normalized
        except Exception as e:
            self.logger.debug("Error fetching available models: %s", e)
            return []

    def get_running_models(self):
        # Check cache first (running models change more frequently)
        cached = self._get_cached('running_models', ttl_seconds=10)  # 10 seconds
        if cached is not None:
            return cached

        try:
            response = self._session.get(self.get_api_url(), timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data.get('models', [])
            current_models = [self._format_running_model_entry(m, include_has_custom_settings=True) for m in models]

            if current_models:
                self.update_history(current_models)

            self._set_cached('running_models', current_models)
            return current_models
        except requests.exceptions.ConnectionError:
            raise Exception("Could not connect to Ollama server. Please ensure it's running and accessible.")
        except requests.exceptions.Timeout:
            raise Exception("Connection to Ollama server timed out. Please check your network connection.")
        except Exception as e:
            raise Exception(f"Error fetching models: {str(e)}")

    def load_history(self):
        if not self.app:
            return deque(maxlen=50)  # Default max history when no app context

        history_file = self.app.config['HISTORY_FILE']
        max_history = self.app.config['MAX_HISTORY']

        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                return deque(history, maxlen=max_history)
        else:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump([], f)
            return deque(maxlen=max_history)

    def update_history(self, models):
        timestamp = datetime.now().isoformat()
        self.history.appendleft({
            'timestamp': timestamp,
            'models': models
        })
        self.save_history()

    def save_history(self):
        if not self.app:
            return  # Skip saving when no app context
        with open(self.app.config['HISTORY_FILE'], 'w', encoding='utf-8') as f:
            json.dump(list(self.history), f)

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
            self.save_history()
        except Exception:
            pass

    def format_datetime(self, value):
        try:
            if isinstance(value, str):
                v = value
                # Normalize 'Z' suffix to '+00:00' for fromisoformat
                if v.endswith('Z'):
                    v = v.replace('Z', '+00:00')
                # Try parsing with optional fractional seconds removed
                try:
                    dt = datetime.fromisoformat(v)
                except Exception:
                    if '.' in v:
                        base = v.split('.')[0]
                        try:
                            dt = datetime.fromisoformat(base)
                        except Exception:
                            return value
                    else:
                        return value
            else:
                dt = value
            # If naive datetime assume UTC then convert to local timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone()
            tz_abbr = local_dt.tzname() or ''
            # Hour without leading zero, minute, AM/PM
            hour = str(int(local_dt.strftime('%I')))
            minute = local_dt.strftime('%M')
            ampm = local_dt.strftime('%p')
            month_abbr = local_dt.strftime('%b')
            day = str(int(local_dt.strftime('%d')))
            return f"{hour}:{minute} {ampm}, {month_abbr} {day} ({tz_abbr})"
        except Exception:
            return str(value)

    def format_time_ago(self, value):
        try:
            if isinstance(value, str):
                # Handle timezone offset in the ISO format string
                dt = datetime.fromisoformat(value.replace('Z', '+00:00').split('.')[0])
            else:
                dt = value

            now = datetime.now(dt.tzinfo)
            diff = now - dt

            minutes = diff.total_seconds() / 60
            hours = minutes / 60

            if hours >= 1:
                return f"{int(hours)} {'hour' if int(hours) == 1 else 'hours'}"
            elif minutes >= 1:
                return f"{int(minutes)} {'minute' if int(minutes) == 1 else 'minutes'}"
            else:
                return "less than a minute"
        except Exception as e:
            return str(value)

    def get_chat_history(self):
        """Get chat history"""
        try:
            if not self.app or not hasattr(self.app, "config"):
                return []
            chat_history_file = os.path.join(os.path.dirname(self.app.config['HISTORY_FILE']), 'chat_history.json')
            if os.path.exists(chat_history_file):
                with open(chat_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            self.logger.exception("Error loading chat history: %s", e)
            return []
    def save_chat_session(self, session_data):
        """Save a chat session"""
        try:
            if not self.app or not hasattr(self.app, "config"):
                return
            chat_history_file = os.path.join(os.path.dirname(self.app.config['HISTORY_FILE']), 'chat_history.json')
            history = self.get_chat_history()

            # Add timestamp if not present
            if 'timestamp' not in session_data:
                session_data['timestamp'] = datetime.now().isoformat()

            history.insert(0, session_data)  # Add to beginning

            # Keep only last 100 sessions
            history = history[:100]

            with open(chat_history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            self.logger.exception("Error saving chat session: %s", e)

    def get_model_performance(self, model_name):
        """Get performance metrics for a model"""
        try:
            # Test model with a simple prompt to measure performance
            import time
            import requests

            test_prompt = "Hello, how are you?"
            start_time = time.time()

            if self.app and hasattr(self.app, "config"):
                host = self.app.config.get('OLLAMA_HOST', 'localhost')
                port = self.app.config.get('OLLAMA_PORT', 11434)
            else:
                host = os.getenv('OLLAMA_HOST', 'localhost')
                port = int(os.getenv('OLLAMA_PORT', 11434))

            response = requests.post(
                f"http://{host}:{port}/api/generate",
                json={
                    "model": model_name,
                    "prompt": test_prompt,
                    "stream": False
                },
                timeout=30
            )

            end_time = time.time()
            response_time = end_time - start_time

            if response.status_code == 200:
                data = response.json()
                response_text = data.get('response', '')
                eval_count = data.get('eval_count', 0)
                eval_duration = data.get('eval_duration', 0)

                # Calculate tokens per second
                tokens_per_sec = eval_count / (eval_duration / 1e9) if eval_duration > 0 else 0

                return {
                    "model": model_name,
                    "response_time": round(response_time, 2),
                    "tokens_generated": eval_count,
                    "tokens_per_second": round(tokens_per_sec, 2),
                    "response_length": len(response_text),
                    "status": "success"
                }
            else:
                return {
                    "model": model_name,
                    "status": "error",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

        except Exception as e:
            return {
                "model": model_name,
                "status": "error",
                "error": str(e)
            }

    def get_system_stats_history(self):
        """Get historical system stats"""
        try:
            if not self.app or not hasattr(self.app, "config"):
                return []
            stats_history_file = os.path.join(os.path.dirname(self.app.config['HISTORY_FILE']), 'system_stats_history.json')

            # Initialize or load existing history
            if os.path.exists(stats_history_file):
                with open(stats_history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            else:
                history = []

            # Add current stats
            current_stats = self.get_system_stats()
            if current_stats:
                current_stats['timestamp'] = datetime.now().isoformat()
                history.append(current_stats)

                # Keep only last 100 entries
                history = history[-100:]

                # Save updated history
                with open(stats_history_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, indent=2)

            return history

        except Exception as e:
            self.logger.exception("Error getting system stats history: %s", e)
            return []

    def get_model_info_cached(self, model_name):
        """Get cached model info to avoid repeated API calls"""
        try:
            # Try to get from running models first
            running_models = self.get_running_models()
            for model in running_models:
                if model.get('name') == model_name:
                    return model

            # If not running, check available models
            available_models = self.get_available_models()
            for model in available_models:
                if model.get('name') == model_name:
                    return model

            return None
        except Exception as e:
            self.logger.exception(f"Error getting model info_cached for {model_name}: {e}")
            return None

    def _has_custom_settings(self, model_name):
        try:
            with self._model_settings_lock:
                if not self._model_settings:
                    self._model_settings = self.load_model_settings() or {}
                entry = self._model_settings.get(model_name)
                return bool(entry) and entry.get('source') == 'user'
        except Exception:
            return False

    # Global settings & autosave toggle removed; per-model recommendations always saved when first seen.

    # ----------------- Model Settings (per-model defaults) -----------------
    def _model_settings_file_path(self):
        return model_settings_file_path(self)

    def load_model_settings(self):
        return load_model_settings(self)

    def _write_model_settings_file(self, model_settings_dict):
        return write_model_settings_file(self, model_settings_dict)

    def get_model_settings(self, model_name):
        return get_model_settings_entry(self, model_name)

    def get_model_settings_with_fallback(self, model_name):
        return get_model_settings_with_fallback_entry(self, model_name)

    def save_model_settings(self, model_name, settings, source='user'):
        return save_model_settings_entry(self, model_name, settings, source)

    def delete_model_settings(self, model_name):
        return delete_model_settings_entry(self, model_name)

    def _ensure_model_settings_exists(self, model_info):
        return ensure_model_settings_exists(self, model_info)


    def _recommend_settings_for_model(self, model_info):
        try:
            return recommend_settings_for_model(self, model_info)
        except Exception as e:
            self.logger.exception(f"Error recommending settings for {model_info}: {e}")
            return self.get_default_settings()

    def _normalize_setting_value(self, key, value, default):
        return normalize_setting_value(key, value, default)

    # Legacy migration from global settings.json removed (no longer supported).

    # ----------------- Service control internal helpers -----------------
    def _start_service_windows(self):
        """Attempt to start Ollama service on Windows using several strategies.
        Returns (result_dict, methods_tried). result_dict is None if not successful yet.
        """
        import subprocess
        methods_tried = []
        if platform.system() != 'Windows':
            return None, methods_tried
        # Method 1: Windows service
        try:
            methods_tried.append('Windows service')
            result = subprocess.run(['sc', 'start', 'Ollama'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0 or 'START_PENDING' in result.stdout:
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via Windows service"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Method 2: direct execution if command exists
        try:
            methods_tried.append('direct execution')
            check = subprocess.run(['where', 'ollama'], capture_output=True, text=True, timeout=5, check=False)
            if check.returncode == 0:
                try:
                    subprocess.Popen(
                        ['ollama', 'serve'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                        close_fds=True
                    )
                except Exception:
                    pass
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via direct execution"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass
        # Method 3: common installation paths
        try:
            methods_tried.append('installation path')
            common_paths = [
                r"C:\Program Files\Ollama\ollama.exe",
                r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe")
            ]
            for path in common_paths:
                expanded = os.path.expandvars(path)
                if os.path.exists(expanded):
                    try:
                        process = subprocess.Popen(
                            [expanded, 'serve'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                            close_fds=True
                        )
                    except Exception:
                        process = None
                    time.sleep(5)
                    if self.get_service_status():
                        return {"success": True, "message": f"Ollama service started successfully from {expanded}"}, methods_tried
        except (OSError, subprocess.SubprocessError):
            pass
        return None, methods_tried

    def _start_service_unix(self):
        """Attempt to start Ollama service on Unix-like systems. Returns (result_dict, methods_tried)."""
        import subprocess
        methods_tried = []
        if platform.system() == 'Windows':
            return None, methods_tried
        # systemctl
        try:
            methods_tried.append('systemctl')
            result = subprocess.run(['systemctl', 'start', 'ollama'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via systemctl"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # service command
        try:
            methods_tried.append('service command')
            result = subprocess.run(['service', 'ollama', 'start'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via service command"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # direct execution
        try:
            methods_tried.append('direct execution')
            check = subprocess.run(['which', 'ollama'], capture_output=True, text=True, timeout=5, check=False)
            if check.returncode == 0:
                try:
                    process = subprocess.Popen(
                        ['ollama', 'serve'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                except Exception:
                    process = None
                time.sleep(5)
                if self.get_service_status():
                    return {"success": True, "message": "Ollama service started successfully via direct execution"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass
        return None, methods_tried

    def _stop_service_windows(self):
        """Attempt to stop service on Windows. Returns (result_dict, methods_tried)."""
        import subprocess
        methods_tried = []
        if platform.system() != 'Windows':
            return None, methods_tried
        # Windows service stop
        try:
            methods_tried.append('Windows service')
            result = subprocess.run(['sc', 'stop', 'Ollama'], capture_output=True, text=True, timeout=15)
            if result.returncode == 0 or 'STOP_PENDING' in result.stdout:
                time.sleep(5)
                if not self.get_service_status():
                    return {"success": True, "message": "Ollama service stopped successfully via Windows service"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Graceful termination
        try:
            methods_tried.append('process termination')
            subprocess.run(['taskkill', '/IM', 'ollama.exe'], capture_output=True, text=True, timeout=10)
            time.sleep(3)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via graceful termination"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Force kill
        try:
            methods_tried.append('force kill')
            subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], capture_output=True, text=True, timeout=10)
            time.sleep(3)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via force kill"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        return None, methods_tried

    def _stop_service_unix(self):
        """Attempt to stop service on Unix-like systems. Returns (result_dict, methods_tried)."""
        import subprocess
        methods_tried = []
        if platform.system() == 'Windows':
            return None, methods_tried
        # systemctl
        try:
            methods_tried.append('systemctl')
            result = subprocess.run(['systemctl', 'stop', 'ollama'], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                time.sleep(5)
                if not self.get_service_status():
                    return {"success": True, "message": "Ollama service stopped successfully via systemctl"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # service command
        try:
            methods_tried.append('service command')
            result = subprocess.run(['service', 'ollama', 'stop'], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                time.sleep(5)
                if not self.get_service_status():
                    return {"success": True, "message": "Ollama service stopped successfully via service command"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # pkill TERM
        try:
            methods_tried.append('pkill graceful')
            subprocess.run(['pkill', '-TERM', '-f', 'ollama'], capture_output=True, text=True, timeout=10)
            time.sleep(3)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via graceful pkill"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # pkill -9
        try:
            methods_tried.append('pkill force')
            subprocess.run(['pkill', '-9', '-f', 'ollama'], capture_output=True, text=True, timeout=10)
            time.sleep(3)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via force pkill"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        # killall TERM
        try:
            methods_tried.append('killall')
            subprocess.run(['killall', '-TERM', 'ollama'], capture_output=True, text=True, timeout=10)
            time.sleep(3)
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service stopped successfully via killall"}, methods_tried
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        return None, methods_tried

    def get_service_status(self):
        """Check if Ollama service is running"""
        try:
            import subprocess
            if platform.system() == "Windows":
                # On Windows, check if ollama.exe process is running
                try:
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ollama.exe', '/NH'],
                        capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        return "ollama.exe" in result.stdout.lower()
                    return False
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    # Try alternative method - check for ollama serve process
                    try:
                        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ollama.exe'],
                            capture_output=True, text=True, timeout=5)
                        return result.returncode == 0 and "ollama.exe" in result.stdout
                    except Exception:
                        return False
            else:
                # On Unix-like systems, use pgrep or ps
                try:
                    result = subprocess.run(['pgrep', '-f', 'ollama'],
                        capture_output=True, text=True, timeout=5)
                    return result.returncode == 0
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    # Fallback to ps command
                    try:
                        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=5)
                        return 'ollama' in result.stdout.lower()
                    except Exception:
                        return False

        except Exception as e:
            self.logger.exception(f"Error checking service status: {str(e)}")
            return False

    def start_service(self):
        """Start the Ollama service"""
        try:
            import subprocess
            # Check if already running
            if self.get_service_status():
                return {"success": True, "message": "Ollama service is already running"}

            if platform.system() == "Windows":
                # On Windows, try multiple methods
                methods_tried = []

                # Method 1: Try Windows service
                try:
                    methods_tried.append("Windows service")
                    result = subprocess.run(['sc', 'start', 'Ollama'],
                        capture_output=True, text=True, timeout=15)
                    if result.returncode == 0 or "START_PENDING" in result.stdout:
                        time.sleep(5)  # Wait longer for service
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via Windows service"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 2: Try running ollama serve directly
                try:
                    methods_tried.append("direct execution")
                    # Check if ollama command exists
                    ollama_check = subprocess.run(['where', 'ollama'],
                                                capture_output=True, text=True, timeout=5)
                    if ollama_check.returncode == 0:
                        # Start ollama serve in background
                        process = subprocess.Popen(
                            ['ollama', 'serve'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                            close_fds=True
                        )
                        time.sleep(5)  # Wait for startup
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via direct execution"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
                    pass

                # Method 3: Try to find and run from common installation paths
                try:
                    methods_tried.append("installation path")
                    common_paths = [
                        r"C:\Program Files\Ollama\ollama.exe",
                        r"C:\Users\%USERNAME%\AppData\Local\Programs\Ollama\ollama.exe",
                        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe")
                    ]

                    for path in common_paths:
                        expanded_path = os.path.expandvars(path)
                        if os.path.exists(expanded_path):
                            process = subprocess.Popen(
                                [expanded_path, 'serve'],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                                close_fds=True
                            )
                            time.sleep(5)
                            if self.get_service_status():
                                return {"success": True, "message": f"Ollama service started successfully from {expanded_path}"}
                except (OSError, subprocess.SubprocessError):
                    pass

            else:
                # On Unix-like systems
                methods_tried = []

                # Method 1: Try systemctl (systemd)
                try:
                    methods_tried.append("systemctl")
                    result = subprocess.run(['systemctl', 'start', 'ollama'],
                                          capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        time.sleep(5)
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via systemctl"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 2: Try service command (init.d)
                try:
                    methods_tried.append("service command")
                    result = subprocess.run(['service', 'ollama', 'start'],
                                          capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        time.sleep(5)
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via service command"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Method 3: Try direct execution
                try:
                    methods_tried.append("direct execution")
                    # Check if ollama command exists
                    ollama_check = subprocess.run(['which', 'ollama'],
                                                capture_output=True, text=True, timeout=5)
                    if ollama_check.returncode == 0:
                        process = subprocess.Popen(
                            ['ollama', 'serve'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            preexec_fn=getattr(os, 'setsid', None)  # Create new process group if available
                        )
                        time.sleep(5)
                        if self.get_service_status():
                            return {"success": True, "message": "Ollama service started successfully via direct execution"}
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
                    pass

            # If we get here, all methods failed
            methods_str = ", ".join(methods_tried) if methods_tried else "no methods"
            return {"success": False, "message": f"Failed to start Ollama service. Tried: {methods_str}. Please ensure Ollama is installed and try starting it manually."}

        except Exception as e:
            return {"success": False, "message": f"Unexpected error starting service: {str(e)}"}

    def stop_service(self):
        try:
            if not self.get_service_status():
                return {"success": True, "message": "Ollama service is already stopped"}
            if platform.system() == 'Windows':
                result, methods = stop_service_windows(self.get_service_status)
            else:
                result, methods = stop_service_unix(self.get_service_status)
            if result:
                return result
            methods_str = ", ".join(methods) if methods else "no methods"
            return {"success": False, "message": f"Failed to stop Ollama service. Tried: {methods_str}."}
        except Exception as e:
            return {"success": False, "message": f"Unexpected error stopping service: {str(e)}"}

    def restart_service(self):
        """Restart the Ollama service"""
        try:
            # Stop background updates temporarily to avoid race conditions during restart
            try:
                if self._background_stats and self._background_stats.is_alive():
                    self._stop_background.set()
                    self._background_stats.join(timeout=5)
            except Exception:
                pass
            stop_result = self.stop_service()
            if not stop_result["success"]:
                # Attempt to proceed if service already stopped
                if "already" not in stop_result.get("message", "").lower():
                    return stop_result

            # Wait a moment before starting
            import time
            time.sleep(2)

            start_result = self.start_service()
            if start_result["success"]:
                # Flush caches and restart background thread
                try:
                    self.clear_all_caches()
                except Exception:
                    pass
                try:
                    self._stop_background.clear()
                    self._start_background_updates()
                except Exception:
                    pass
                return {"success": True, "message": "Ollama service restarted successfully (caches & background refreshed)"}
            else:
                # Attempt to restart background updates even on failure to avoid stale thread state
                try:
                    self._stop_background.clear()
                    self._start_background_updates()
                except Exception:
                    pass
                return start_result

        except Exception as e:
            return {"success": False, "message": f"Unexpected error restarting service: {str(e)}"}

    def full_restart(self):
        """Comprehensive application restart: clear caches, reload model settings, restart background thread, return health. Does NOT restart Ollama service."""
        try:
            # Clear all caches
            try:
                self.clear_all_caches()
            except Exception:
                pass
            # Reload model settings to pick up external changes
            try:
                self._model_settings = self.load_model_settings()
            except Exception:
                pass
            # Ensure background thread running
            try:
                if not (self._background_stats and self._background_stats.is_alive()):
                    self._stop_background.clear()
                    self._start_background_updates()
            except Exception:
                pass
            return {"success": True, "message": "Full application restart completed", "health": self.get_component_health()}
        except Exception as e:
            return {"success": False, "message": f"Unexpected error performing full restart: {str(e)}"}

    def get_models_memory_usage(self):
        try:
            running_models = self.get_running_models()
            return models_memory_usage(running_models)
        except Exception as e:
            self.logger.exception(f"Error getting models memory usage: {str(e)}")
            return {
                'system_ram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
                'system_vram': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
                'models': [],
                'error': str(e)
            }

    # Duplicate legacy implementations of get_downloadable_models/pull_model removed.
    # Unified versions with category support are defined later in file.

    # Global settings file (settings.json) removed; defaults returned directly below.

    def get_default_settings(self):
        """Return base default per-model generation settings (global settings deprecated)."""
        return {
            "temperature": 0.7,
            "top_k": 40,
            "top_p": 0.9,
            "num_ctx": 2048,
            "seed": 0,
            # Advanced sampling / prediction controls
            "num_predict": 256,
            "repeat_last_n": 64,
            "repeat_penalty": 1.1,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "stop": [],
            "min_p": 0.05,
            "typical_p": 1.0,
            "penalize_newline": False,
            # Mirostat adaptive sampling disabled by default
            "mirostat": 0,
            "mirostat_tau": 5.0,
            "mirostat_eta": 0.1
        }

    # Delegated model catalog methods (moved to model_catalog.py)
    def get_best_models(self):
        from app.services.model_catalog import get_best_models as _get_best
        return _get_best()

    def get_all_downloadable_models(self):
        from app.services.model_catalog import get_all_downloadable_models as _get_all
        return _get_all()

    def get_downloadable_models(self, category='best'):
        from app.services.model_catalog import get_downloadable_models as _get_dl
        return _get_dl(category)

    def pull_model(self, model_name):
        """Pull a model from the Ollama library."""
        try:
            if self.app:
                host = self.app.config.get('OLLAMA_HOST')
                port = self.app.config.get('OLLAMA_PORT')
            else:
                host = os.getenv('OLLAMA_HOST', 'localhost')
                port = int(os.getenv('OLLAMA_PORT', 11434))

            pull_url = f"http://{host}:{port}/api/pull"

            response = self._session.post(
                pull_url,
                json={"name": model_name, "stream": False},
                timeout=3600
            )

            if response.status_code == 200:
                return {"success": True, "message": f"Model {model_name} pulled successfully"}
            else:
                return {"success": False, "message": f"Failed to pull model: {response.text}"}

        except Exception as e:
            return {"success": False, "message": str(e)}

