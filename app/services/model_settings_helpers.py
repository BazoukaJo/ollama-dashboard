"""Model settings helper functions extracted from OllamaService to reduce file length.
Operate on a service instance passed as first argument.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
import tempfile
# Remove unused and invalid imports; _recommend_settings_for_model should be accessed via the service instance

# Default template retained from service logic
_DEF_TEMPLATE = {
    # Averages aligned with common Ollama / llama.cpp chat use (balanced quality vs coherence).
    'temperature': 0.75,
    'top_k': 40,
    'top_p': 0.9,
    'num_ctx': 4096,
    'seed': 0,
    'num_predict': 512,
    'repeat_last_n': 64,
    'repeat_penalty': 1.05,
    'presence_penalty': 0.0,
    'frequency_penalty': 0.0,
    'stop': [],
    'min_p': 0.05,
    'typical_p': 1.0,
    'penalize_newline': False,
    'mirostat': 0,
    'mirostat_tau': 5.0,
    'mirostat_eta': 0.1,
}

def get_default_settings_template():
    return dict(_DEF_TEMPLATE)


def normalize_model_settings_key(model_name):
    """Canonical dict key for per-model settings (matches Ollama API name strings)."""
    if model_name is None:
        return ''
    return str(model_name).strip()


def lookup_settings_entry(model_settings, model_name):
    """Return the settings entry dict for ``model_name``, or None.

    Keys in persisted JSON may differ by surrounding whitespace from API ``name``;
    match using stripped equality.
    """
    if not isinstance(model_settings, dict):
        return None
    want = normalize_model_settings_key(model_name)
    if not want:
        return None
    if want in model_settings:
        entry = model_settings[want]
        return entry if isinstance(entry, dict) else None
    for k, v in model_settings.items():
        if normalize_model_settings_key(k) == want:
            return v if isinstance(v, dict) else None
    return None


def model_settings_file_path(service):
    if service.app:
        return service.app.config.get('MODEL_SETTINGS_FILE', 'model_settings.json')
    return os.getenv('MODEL_SETTINGS_FILE', 'model_settings.json')

def load_model_settings(service):
    path = model_settings_file_path(service)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        service.logger.exception("Error loading model settings")  # Narrowed exception handling
        return {}

def write_model_settings_file(service, model_settings_dict):
    """Atomically replace the settings file (temp in same dir, fsync, os.replace)."""
    ok, err = validate_json_before_write(model_settings_dict)
    if not ok:
        service.logger.error("Refusing to write invalid model settings JSON: %s", err)
        return False
    path = model_settings_file_path(service)
    abs_path = os.path.abspath(path)
    dirpath = os.path.dirname(abs_path) or "."
    try:
        os.makedirs(dirpath, exist_ok=True)
    except OSError as e:
        service.logger.exception("Cannot create settings directory %s: %s", dirpath, e)
        return False
    fd, tmp_path = tempfile.mkstemp(
        prefix="model_settings_",
        suffix=".tmp",
        dir=dirpath,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(model_settings_dict, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, abs_path)
        tmp_path = None
        try:
            service._model_settings_disk_mtime = os.path.getmtime(abs_path)
        except OSError:
            service._model_settings_disk_mtime = None
        return True
    except (OSError, TypeError) as e:
        service.logger.exception("Error writing model settings: %s", e)
        return False
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

def validate_json_before_write(data):
    """Validate that data can be JSON serialized before writing to file."""
    try:
        json.dumps(data)
        return True, None
    except (ValueError, TypeError) as e:
        return False, str(e)

def merge_model_info_for_recommendation(service, model_name, hint=None):
    """Merge list cache + optional caller hint + /api/show for accurate defaults after pull."""
    name = model_name or (hint or {}).get("name")
    if not name:
        return {"name": str(model_name)}
    merged = {}
    if isinstance(hint, dict):
        merged.update(hint)
    try:
        cached = service.get_model_info_cached(name)
    except Exception:
        cached = None
    if isinstance(cached, dict):
        merged = {**cached, **merged, "name": name}
    else:
        merged.setdefault("name", name)
    try:
        detailed = service.get_detailed_model_info(name)
    except Exception:
        detailed = None
    if isinstance(detailed, dict):
        merged = {**merged, **detailed, "name": name}
    return merged


def normalize_setting_value(key, value, default_val):
    try:
        if key == 'stop':
            if isinstance(value, list):
                return [str(v) for v in value][:10]
            if isinstance(value, str):
                parts = [p.strip() for p in value.split(',') if p.strip()]
                return parts[:10]
            return []
        if isinstance(default_val, (int, float)):
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                try:
                    return float(value) if isinstance(default_val, float) else int(value)
                except Exception:
                    return default_val
        if isinstance(default_val, bool):
            return bool(value)
        return value if type(value) is type(default_val) else default_val
    except Exception:
        return default_val

def ensure_model_settings_exists(service, model_info):
    try:
        model_name = model_info.get('name') if isinstance(model_info, dict) else str(model_info)
        with service._model_settings_lock:
            if not service._model_settings:
                service._model_settings = load_model_settings(service) or {}
            if model_name in service._model_settings:
                return service._model_settings[model_name]

        merged = merge_model_info_for_recommendation(service, model_name, model_info)
        recommended = service._recommend_settings_for_model(merged)
        entry = {
            'settings': recommended,
            'source': 'recommended',
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        with service._model_settings_lock:
            service._model_settings[model_name] = entry
            write_model_settings_file(service, service._model_settings)
        return entry
    except Exception as e:
        service.logger.exception(f"Error getting model settings for {model_name}: {e}")
        return None

def get_model_settings_with_fallback_entry(service, model_name):
    try:
        with service._model_settings_lock:
            if not service._model_settings:
                service._model_settings = load_model_settings(service) or {}
            if model_name in service._model_settings:
                return service._model_settings[model_name]

        merged = merge_model_info_for_recommendation(service, model_name, None)
        recommended = service._recommend_settings_for_model(merged)
        entry = {
            'settings': recommended,
            'source': 'recommended',
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        with service._model_settings_lock:
            service._model_settings[model_name] = entry
            write_model_settings_file(service, service._model_settings)
        return entry
    except Exception as e:
        service.logger.exception(f"Error getting model settings with fallback for {model_name}: {e}")
    return {
        'settings': get_default_settings_template(),
        'source': 'default',
        'last_updated': datetime.now(timezone.utc).isoformat()
    }

def delete_model_settings_entry(service, model_name):
    try:
        want = normalize_model_settings_key(model_name)
        if not want:
            return False
        with service._model_settings_lock:
            if not service._model_settings:
                service._model_settings = load_model_settings(service) or {}
            if want in service._model_settings:
                del service._model_settings[want]
                write_model_settings_file(service, service._model_settings)
                return True
            for k in list(service._model_settings.keys()):
                if normalize_model_settings_key(k) == want:
                    del service._model_settings[k]
                    write_model_settings_file(service, service._model_settings)
                    return True
        return False
    except Exception as e:
        service.logger.exception(f"Error deleting model settings for {model_name}: {e}")
        return False
