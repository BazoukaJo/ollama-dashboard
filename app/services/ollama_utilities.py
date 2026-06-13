"""Utility functions for OllamaService: history, formatting, performance, settings, and defaults."""

import json
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import requests

from app.services.model_fetcher import get_all_downloadable_models_live as _get_all
from app.services.model_fetcher import get_best_models_live as _get_best
from app.services.model_fetcher import get_downloadable_models_live as _get_dl
from app.services.model_helpers import context_length_as_int
from app.services.model_recommendation_profiles import (
    apply_profile_settings,
    match_recommendation_profile,
    resolve_num_ctx_for_model,
)
from app.services.model_settings_helpers import (
    compute_fresh_recommended_settings_entry,
    delete_model_settings_entry,
    ensure_model_settings_exists,
    get_default_settings_template,
    get_existing_model_settings_entry,
    get_model_settings_with_fallback_entry,
    load_model_settings,
    model_settings_file_path,
    normalize_model_settings_key,
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
    _model_settings_disk_mtime: Optional[float] = None
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
            with open(history_file, encoding='utf-8') as f:
                history = json.load(f)
                return deque(history, maxlen=max_history)
        else:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump([], f)
            return deque(maxlen=max_history)

    def update_history(self, models):
        """Update history with latest model list."""
        if self.history is None:
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
        if self.history is None:
            return  # Skip saving when no history available
        try:
            # Validate JSON serialization before write
            json_str = json.dumps(list(self.history))
            history_file = self.app.config['HISTORY_FILE']
            history_dir = os.path.dirname(os.path.abspath(history_file)) or '.'
            os.makedirs(history_dir, exist_ok=True)
            # Write with atomic pattern: tmp then rename
            tmp_path = history_file + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            try:
                os.replace(tmp_path, history_file)
            except PermissionError:
                time.sleep(0.02)
                try:
                    os.replace(tmp_path, history_file)
                except OSError:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
        except (ValueError, TypeError, OSError) as e:
            self.logger.warning(f"Failed to serialize history: {e}")

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
                with open(chat_history_file, encoding='utf-8') as f:
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

            response = self._session.post(
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
                with open(stats_history_file, encoding='utf-8') as f:
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

    def refresh_model_settings_cache_from_disk(self):
        """Reload in-memory ``_model_settings`` from the JSON file on disk.

        Call once per request before iterating models for ``has_custom_settings``:
        the cache can otherwise stay non-empty but stale (another worker wrote the
        file, or the file was updated outside this process).
        """
        lock = getattr(self, '_model_settings_lock', None)
        path = self._model_settings_file_path()
        try:
            disk_mtime = os.path.getmtime(path)
        except OSError:
            disk_mtime = None

        # Skip disk I/O when file has not changed.
        known_mtime = getattr(self, '_model_settings_disk_mtime', None)
        if known_mtime == disk_mtime and isinstance(getattr(self, '_model_settings', None), dict):
            return

        if lock is not None:
            with lock:
                self._model_settings = self.load_model_settings() or {}
                self._model_settings_disk_mtime = disk_mtime
        else:
            self._model_settings = self.load_model_settings() or {}
            self._model_settings_disk_mtime = disk_mtime

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

        canon_key = normalize_model_settings_key(model_name)
        if not canon_key:
            return False

        self._model_settings = getattr(self, '_model_settings', {})
        self._model_settings[canon_key] = entry

        lock = getattr(self, '_model_settings_lock', None)
        if lock is not None:
            with lock:
                return self._write_model_settings_file(self._model_settings)
        else:
            return self._write_model_settings_file(self._model_settings)

    def delete_model_settings(self, model_name):
        """Delete settings for a specific model."""
        return delete_model_settings_entry(self, model_name)

    # PARAMETER directives recognized by Ollama Modelfiles. Keys outside this
    # set (e.g. presence_penalty, frequency_penalty, typical_p, penalize_newline)
    # are accepted as per-request `options` but are not valid Modelfile parameters.
    _MODELFILE_PARAMETER_KEYS = (
        'mirostat', 'mirostat_eta', 'mirostat_tau', 'num_ctx', 'repeat_last_n',
        'repeat_penalty', 'temperature', 'seed', 'stop', 'num_predict',
        'top_k', 'top_p', 'min_p',
    )

    def derived_model_name(self, model_name):
        """Name used for the baked-in derived model created from `model_name`."""
        base, sep, tag = model_name.partition(':')
        return f"{base}-dashboard{sep}{tag}" if sep else f"{base}-dashboard"

    def build_modelfile(self, model_name, settings):
        """Build Modelfile text that bakes `settings` into a model derived from `model_name`."""
        lines = [f"FROM {model_name}"]
        for key in self._MODELFILE_PARAMETER_KEYS:
            if key not in settings:
                continue
            value = settings[key]
            if key == 'stop':
                for stop_seq in (value or []):
                    lines.append(f'PARAMETER stop "{stop_seq}"')
                continue
            if isinstance(value, bool):
                value = 'true' if value else 'false'
            lines.append(f"PARAMETER {key} {value}")
        return "\n".join(lines) + "\n"

    def bake_model_settings(self, model_name, derived_name=None):
        """Create a derived Ollama model with the saved per-model settings baked in
        as Modelfile PARAMETER directives, so external clients (VS Code, `ollama run`,
        other apps hitting the Ollama API directly) get the same defaults the
        dashboard applies to its own requests.

        Returns a dict: {"success": bool, "model": <derived name>, "message": str}
        """
        if self._session is None:
            return {"success": False, "message": "Session not initialized"}

        entry = self.get_model_settings_with_fallback(model_name)
        settings = entry.get('settings') if isinstance(entry, dict) else None
        if not isinstance(settings, dict):
            return {"success": False, "message": f"No settings available for {model_name}"}

        target_name = derived_name or self.derived_model_name(model_name)
        modelfile = self.build_modelfile(model_name, settings)

        try:
            host, port = self._get_ollama_host_port()
            create_url = f"http://{host}:{port}/api/create"
            response = self._session.post(
                create_url,
                json={"model": target_name, "modelfile": modelfile, "stream": False},
                timeout=600,
            )
            if response.status_code == 200:
                return {
                    "success": True,
                    "model": target_name,
                    "modelfile": modelfile,
                    "message": f"Created {target_name} with your saved settings baked in. "
                               f"Use '{target_name}' in VS Code or other external clients to get these defaults.",
                }
            return {"success": False, "message": f"Failed to create {target_name}: {response.text}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

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

        def _safe_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _bytes_to_gb(v):
            as_float = _safe_float(v)
            if as_float is None or as_float <= 0:
                return 0.0
            return as_float / (1024 ** 3)

        def _param_size_to_float(param_size):
            try:
                if isinstance(param_size, (int, float)):
                    return float(param_size)
                if isinstance(param_size, str):
                    # Handles formats like "14B", "1.8B", and MoE style "8x7B".
                    s = param_size.strip().upper().replace(' ', '')
                    moe_match = re.match(r'^(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)B$', s)
                    if moe_match:
                        experts = float(moe_match.group(1))
                        per_expert = float(moe_match.group(2))
                        # Use active expert size approximation to avoid over-allocating defaults.
                        return max(per_expert, experts)
                    num_match = re.match(r'^(\d+(?:\.\d+)?)B$', s)
                    if num_match:
                        return float(num_match.group(1))
            except Exception:
                return None
            return None

        def _resource_ctx_cap():
            """Compute a conservative num_ctx cap from available machine memory.

            This keeps defaults efficient on modest rigs while still allowing larger
            context windows on stronger systems.
            """
            try:
                stats = self.get_system_stats() if hasattr(self, 'get_system_stats') else {}
            except Exception:
                stats = {}

            mem = stats.get('memory', {}) if isinstance(stats, dict) else {}
            vram = stats.get('vram', {}) if isinstance(stats, dict) else {}
            ram_gb = _bytes_to_gb(mem.get('total'))
            vram_gb = _bytes_to_gb(vram.get('total'))

            # Prefer VRAM when detected; otherwise fall back to RAM bands.
            if vram_gb >= 24:
                return 24576
            if vram_gb >= 16:
                return 20480
            if vram_gb >= 12:
                return 16384
            if vram_gb >= 8:
                return 12288
            if vram_gb > 0:
                return 8192

            if ram_gb >= 64:
                return 24576
            if ram_gb >= 32:
                return 16384
            if ram_gb >= 16:
                return 12288
            return 8192

        settings = get_default_settings_template()
        is_coding_model = any(k in name_l for k in (
            'coder', 'code', 'codellama', 'starcoder', 'deepseek-coder', 'devstral',
        ))
        is_unreal_workflow = any(k in name_l for k in ('unreal', 'ue5', 'blueprint', 'cpp', 'c++'))
        code_first_profile = is_coding_model or is_unreal_workflow
        ctx_cap = _resource_ctx_cap()
        param_size = _param_size_to_float(details.get('parameter_size'))

        # Light parameter-size nudges (profile + context resolver apply stronger defaults).
        if param_size is not None:
            if param_size <= 2:
                settings['num_predict'] = max(settings['num_predict'], 512)
            elif param_size <= 8:
                settings['num_predict'] = max(settings['num_predict'], 768)
            elif param_size <= 14:
                settings['num_predict'] = max(settings['num_predict'], 896)
            else:
                settings['num_predict'] = max(settings['num_predict'], 1024)

        # Benchmark-backed family profile (Qwen3, DeepSeek-R1, Llama 3, coders, etc.).
        profile = match_recommendation_profile(info)
        max_ctx = context_length_as_int(info)
        apply_profile_settings(settings, profile, max_ctx=max_ctx, ctx_cap=ctx_cap)

        # Capability flags after profile (tool/vision metadata refines profile defaults).
        if info.get('has_vision') or 'vision' in families or 'llava' in name_l:
            settings['num_predict'] = max(settings['num_predict'], 1024)
        if info.get('has_tools') or 'tool' in name_l:
            settings['top_k'] = min(settings.get('top_k', 40), 20)
        if info.get('has_reasoning'):
            settings['temperature'] = min(settings.get('temperature', 0.75), 0.6)
            settings['num_predict'] = max(settings['num_predict'], 8192)

        # Unreal / niche coding workflows without a catalog profile match.
        if code_first_profile and not profile:
            settings['temperature'] = min(settings['temperature'], 0.32)
            settings['top_p'] = min(settings.get('top_p', 0.9), 0.9)
            settings['top_k'] = min(settings.get('top_k', 40), 30)
            settings['repeat_penalty'] = max(settings.get('repeat_penalty', 1.05), 1.1)
            settings['num_predict'] = max(settings.get('num_predict', 512), 4096)

        settings['num_ctx'] = resolve_num_ctx_for_model(
            settings, max_ctx=max_ctx, ctx_cap=ctx_cap, param_size=param_size,
        )

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
        """Get downloadable models filtered by category.
        Enriches with context_length from the provider (Ollama /api/show) when the model is installed.
        """
        models = _get_dl(category)
        if not models:
            return models
        try:
            available = self.get_available_models()
        except Exception:
            available = []
        by_name = {m.get('name'): m for m in available if isinstance(m, dict) and m.get('name')}
        for entry in models:
            name = entry.get('name')
            if not name:
                continue
            src = by_name.get(name)
            if isinstance(src, dict) and src.get('context_length') is not None:
                entry['context_length'] = src['context_length']
        return models

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

    def pull_model_stream(self, model_name):
        """Stream pull status updates for a model as JSON-friendly events."""
        try:
            if self._session is None:
                yield {"event": "error", "message": "Session not initialized"}
                return

            host, port = self._get_ollama_host_port()
            pull_url = f"http://{host}:{port}/api/pull"

            with self._session.post(
                pull_url,
                json={"name": model_name, "stream": True},
                stream=True,
                timeout=3700,
            ) as response:
                if response.status_code != 200:
                    yield {"event": "error", "message": f"Failed to pull model: {response.text}"}
                    return

                for line in response.iter_lines():
                    if not line:
                        continue

                    try:
                        payload = json.loads(line.decode("utf-8"))
                    except Exception:
                        yield {"event": "status", "message": line.decode("utf-8", errors="ignore")}
                        continue

                    if payload.get("error"):
                        yield {"event": "error", "message": payload.get("error")}
                        return

                    status_msg = payload.get("status") or payload.get("status_message")
                    total = payload.get("total")
                    completed = payload.get("completed")

                    event_payload = {"event": "status"}
                    if status_msg:
                        event_payload["message"] = status_msg
                    if total is not None and completed is not None:
                        event_payload["total"] = total
                        event_payload["completed"] = completed

                    if len(event_payload) > 1:
                        yield event_payload

                    if payload.get("done") or status_msg == "success":
                        yield {"event": "done", "success": True, "message": f"Model {model_name} pulled successfully"}
                        return

                # Fallback completion event when stream ends without explicit done
                yield {"event": "done", "success": True, "message": f"Model {model_name} pulled successfully"}

        except Exception as e:
            yield {"event": "error", "message": str(e)}
