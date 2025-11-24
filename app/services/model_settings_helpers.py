"""Model settings helper functions extracted from OllamaService to reduce file length.
Operate on a service instance passed as first argument.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
# Remove unused and invalid imports; _recommend_settings_for_model should be accessed via the service instance

# Default template retained from service logic
_DEF_TEMPLATE = {
    'temperature': 0.7,
    'top_k': 40,
    'top_p': 0.9,
    'num_ctx': 2048,
    'seed': 0,
    'num_predict': 256,
    'repeat_last_n': 64,
    'repeat_penalty': 1.1,
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
    path = model_settings_file_path(service)
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(model_settings_dict, f, indent=2)
        os.replace(tmp_path, path)
        return True
    except (OSError, TypeError) as e:
        service.logger.exception("Error writing model settings: %s", e)
        return False

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
                return 'exists'
        recommended = service._recommend_settings_for_model(model_info)
        if model_name in service._model_settings:
            return service._model_settings[model_name]
        model_info = service.get_model_info_cached(model_name) or {'name': model_name}
        recommended = service._recommend_settings_for_model(model_info)
        if model_name in service._model_settings:
            return service._model_settings[model_name]
        model_info = service.get_model_info_cached(model_name) or {'name': model_name}
        recommended = service._recommend_settings_for_model(model_info)
        entry = {
            'settings': recommended,
            'source': 'recommended',
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
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
        model_info = service.get_model_info_cached(model_name) or {'name': model_name}
        recommended = service._recommend_settings_for_model(model_info)
        return {
            'settings': recommended,
            'source': 'recommended',
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        service.logger.exception(f"Error getting model settings with fallback for {model_name}: {e}")
    return {
        'settings': get_default_settings_template(),
        'source': 'default',
        'last_updated': datetime.now(timezone.utc).isoformat()
    }

def delete_model_settings_entry(service, model_name):
    try:
        with service._model_settings_lock:
            if not service._model_settings:
                service._model_settings = load_model_settings(service) or {}
            if model_name in service._model_settings:
                del service._model_settings[model_name]
                write_model_settings_file(service, service._model_settings)
                return True
        return False
    except Exception as e:
        service.logger.exception(f"Error deleting model settings for {model_name}: {e}")
        return False
