"""Utility functions for OllamaService: history, formatting, performance, settings, and defaults."""

import json
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import requests
from app.services.model_catalog import get_best_models as _get_best
from app.services.model_catalog import get_all_downloadable_models as _get_all
from app.services.model_catalog import get_downloadable_models as _get_dl
from app.services.model_settings_helpers import (
    delete_model_settings_entry,
    ensure_model_settings_exists,
    get_default_settings_template,
    get_model_settings_with_fallback_entry,
    load_model_settings,
    model_settings_file_path,
    normalize_setting_value,
    write_model_settings_file,
)


class OllamaServiceUtilities:
    """Utility functions for OllamaService: history, formatting, performance, and settings.

    Note: This mixin expects the following attributes/methods from OllamaServiceCore:
    - self.app, self.logger, self.history, self._model_settings_lock,
    - self._model_settings, self._get_ollama_host_port(), self._session
    And from OllamaServiceModels:
    - self.get_system_stats()
    """
    # pylint: disable=no-member

    # Type hints for attributes provided by parent classes
    # Note: These are type hints only - actual attributes are initialized in OllamaServiceCore.__init__
    app: Any = None
    logger: Any = None
    history: Optional[deque] = None  # deque imported at module level
    _model_settings_lock: Any = None  # Initialized in OllamaServiceCore.__init__ as threading.Lock()
    _model_settings: dict = {}  # Initialized in OllamaServiceCore.__init__
    _session: Optional[requests.Session] = None  # Initialized in OllamaServiceCore.__init__

    def _get_ollama_host_port(self) -> Tuple[str, int]:
        """Stub for method provided by parent class."""
        raise NotImplementedError("_get_ollama_host_port must be implemented by parent class")

    # Note: get_system_stats() is provided by OllamaServiceModels mixin

    def load_history(self):
        """Load conversation history from file."""
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
        """Update history with latest model list."""
        if not self.history:
            return  # Skip update when no history available
        timestamp = datetime.now().isoformat()
        self.history.appendleft({
            'timestamp': timestamp,
            'models': models
        })
        self.save_history()
    def save_history(self):
        """Save history to file."""
        if not self.app:
            return  # Skip saving when no app context
        if not self.history:
            return  # Skip saving when no history available
        with open(self.app.config['HISTORY_FILE'], 'w', encoding='utf-8') as f:
            json.dump(list(self.history), f)

    def format_size(self, size_bytes):
        """Format byte size to human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"

    def format_relative_time(self, target_dt):
        """Format time difference as relative time string."""
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

    def format_datetime(self, value):
        """Format ISO datetime to local timezone with time abbreviation."""
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
            return f"{month_abbr} {day}, {hour}:{minute} {ampm} {tz_abbr}"
        except Exception:
            return str(value)

    def format_time_ago(self, value):
        """Format datetime as time elapsed since then (e.g., '2 hours ago')."""
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
        except Exception:
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
            test_prompt = "Hello, how are you?"
            start_time = time.time()

            host = self.app.config.get('OLLAMA_HOST', 'localhost')
            port = self.app.config.get('OLLAMA_PORT', 11434)

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
            try:
                if hasattr(self, "get_system_stats") and callable(getattr(self, "get_system_stats")):
                    stats_result = self.get_system_stats()  # type: ignore
                    if stats_result and isinstance(stats_result, dict):
                        stats_result['timestamp'] = datetime.now().isoformat()  # type: ignore[func-returns-value]
                        history.append(stats_result)

                        # Keep only last 100 entries
                        history = history[-100:]

                        # Save updated history
                        with open(stats_history_file, 'w', encoding='utf-8') as f:
                            json.dump(history, f, indent=2)
            except (NotImplementedError, AttributeError):
                pass

            return history

        except Exception as e:
            self.logger.exception("Error getting system stats history: %s", e)
            return []

    def _model_settings_file_path(self):
        """Get the path to the model settings file."""
        return model_settings_file_path(self)

    def load_model_settings(self):
        """Load per-model settings from file."""
        return load_model_settings(self)

    def _write_model_settings_file(self, model_settings_dict):
        """Write per-model settings to file atomically."""
        return write_model_settings_file(self, model_settings_dict)

    def get_model_settings(self, model_name):
        """Get settings for a specific model with fallback to defaults."""
        return get_model_settings_with_fallback_entry(self, model_name)

    def get_model_settings_with_fallback(self, model_name):
        """Get model settings with fallback entry."""
        return get_model_settings_with_fallback_entry(self, model_name)

    def save_model_settings(self, model_name, settings, source='user'):
        """Save settings for a specific model (normalized, persisted)."""
        template = get_default_settings_template()
        normalized = {}
        for key, default_val in template.items():
            incoming = settings.get(key, default_val) if isinstance(settings, dict) else default_val
            normalized[key] = normalize_setting_value(key, incoming, default_val)

        entry = {
            "settings": normalized,
            "source": source,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        lock = getattr(self, '_model_settings_lock', None)
        if lock is None:
            self._model_settings = getattr(self, '_model_settings', {})
            self._model_settings[model_name] = entry
            return self._write_model_settings_file(self._model_settings)

        with lock:
            self._model_settings = getattr(self, '_model_settings', {})
            self._model_settings[model_name] = entry
            return self._write_model_settings_file(self._model_settings)

    def delete_model_settings(self, model_name):
        """Delete settings for a specific model."""
        return delete_model_settings_entry(self, model_name)

    def _ensure_model_settings_exists(self, model_info):
        """Ensure model settings exist, creating defaults if needed."""
        return ensure_model_settings_exists(self, model_info)

    def _recommend_settings_for_model(self, _model_info):
        """Recommend default settings for a model based on its characteristics."""
        info = _model_info or {}
        details = info.get('details', {}) if isinstance(info, dict) else {}
        families = [f.lower() for f in details.get('families', []) or []]
        name = (info.get('name') or '') if isinstance(info, dict) else str(info)
        name_l = name.lower()

        def _param_size_to_float(param_size):
            try:
                if isinstance(param_size, (int, float)):
                    return float(param_size)
                if isinstance(param_size, str):
                    s = param_size.strip().upper().replace('B', '')
                    return float(s)
            except Exception:
                return None
            return None

        settings = get_default_settings_template()

        # Base heuristics by parameter size
        param_size = _param_size_to_float(details.get('parameter_size'))
        if param_size is not None:
            if param_size <= 2:
                settings['temperature'] = max(settings['temperature'], 0.75)
                settings['num_ctx'] = max(settings['num_ctx'], 2048)
                settings['num_predict'] = max(settings['num_predict'], 256)
            elif param_size <= 8:
                settings['temperature'] = min(max(settings['temperature'], 0.65), 0.75)
                settings['num_ctx'] = max(settings['num_ctx'], 2048)
                settings['num_predict'] = max(settings['num_predict'], 300)
            else:
                settings['temperature'] = min(settings['temperature'], 0.65)
                settings['num_ctx'] = max(settings['num_ctx'], 4096)
                settings['num_predict'] = max(settings['num_predict'], 320)

        # Capabilities heuristics
        if info.get('has_vision') or 'vision' in families or 'llava' in name_l:
            settings['num_ctx'] = max(settings['num_ctx'], 4096)
            settings['top_p'] = max(settings['top_p'], 0.9)
        if info.get('has_reasoning') or 'deepseek' in name_l:
            settings['num_ctx'] = max(settings['num_ctx'], 4096)
            settings['temperature'] = min(settings['temperature'], 0.65)
        if info.get('has_tools') or 'tool' in name_l:
            settings['top_k'] = min(settings.get('top_k', 40), 20)

        # Family-specific nudges
        if 'qwen' in families or 'qwen' in name_l:
            settings['repeat_penalty'] = max(settings['repeat_penalty'], 1.05)
            settings['num_predict'] = max(settings['num_predict'], 320)

        return settings

    def get_default_settings(self):
        """Return base default per-model generation settings (global settings deprecated)."""
        base = get_default_settings_template()
        # Maintain legacy key for compatibility
        base.setdefault("top_k_full_last_n", False)
        return base

    # Delegated model catalog methods (moved to model_catalog.py)
    def get_best_models(self):
        """Get list of best recommended models."""
        return _get_best()

    def get_all_downloadable_models(self):
        """Get list of all downloadable models."""
        return _get_all()

    def get_downloadable_models(self, category='best'):
        """Get downloadable models filtered by category."""
        return _get_dl(category)

    def pull_model(self, model_name):
        """Pull a model from the Ollama library."""
        try:
            if self._session is None:
                return {"success": False, "message": "Session not initialized"}

            host, port = self._get_ollama_host_port()
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
