"""Model settings helper functions extracted from OllamaService to reduce file length.
Operate on a service instance passed as first argument.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os

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
    except (json.JSONDecodeError, OSError) as e:
        service.logger.exception("Error loading model settings: %s", e)
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

def recommend_settings_for_model(service, model_info):
    template = get_default_settings_template()
    recommendations = dict(template)
    details = (model_info.get('details') if isinstance(model_info, dict) else {}) or {}
    param = details.get('parameter_size') or details.get('parameterCount') or ''
    name = (model_info.get('name', '') if isinstance(model_info, dict) else str(model_info))
    name = name.lower() if name else ''
    families = details.get('families') or []
    has_vision = model_info.get('has_vision', False) if isinstance(model_info, dict) else False
    has_tools = model_info.get('has_tools', False) if isinstance(model_info, dict) else False
    has_reasoning = model_info.get('has_reasoning', False) if isinstance(model_info, dict) else False

    size_billion = None
    try:
        if isinstance(param, str):
            p = param.lower().replace(',', '').strip().split('/')[0]
            num_str = ''.join([c for c in p if (c.isdigit() or c == '.')])
            if num_str:
                val = float(num_str)
                if 'gb' in p:
                    size_billion = val
                elif 'mb' in p:
                    size_billion = val / 1000.0
                elif 'kb' in p:
                    size_billion = val / 1000000.0
                elif p.endswith('b') and not p.endswith('gb'):
                    size_billion = val
                else:
                    size_billion = val
    except Exception:
        size_billion = None

    if size_billion is not None:
        if size_billion <= 2:
            recommendations['temperature'] = 0.8
            recommendations['top_k'] = max(40, recommendations.get('top_k', 40))
            recommendations['num_ctx'] = min(4096, recommendations.get('num_ctx', 2048))
            recommendations['num_predict'] = 512
        elif size_billion <= 8:
            recommendations['temperature'] = 0.7
            recommendations['top_k'] = 40
            recommendations['num_ctx'] = max(2048, recommendations.get('num_ctx', 2048))
        elif size_billion <= 30:
            recommendations['temperature'] = 0.65
            recommendations['top_k'] = 40
            recommendations['num_ctx'] = max(4096, recommendations.get('num_ctx', 4096))
        else:
            recommendations['temperature'] = 0.6
            recommendations['top_k'] = 40
            recommendations['num_ctx'] = max(8192, recommendations.get('num_ctx', 8192))

    if has_vision:
        recommendations['num_ctx'] = max(recommendations['num_ctx'], 4096)
    if has_reasoning:
        recommendations['temperature'] = min(recommendations['temperature'], 0.65)
        recommendations['repeat_penalty'] = 1.08
        recommendations['num_ctx'] = max(recommendations.get('num_ctx', 2048), 4096)
    if has_tools:
        recommendations['presence_penalty'] = 0.1
        recommendations['top_k'] = min(recommendations.get('top_k', 40), 20)
        if recommendations.get('num_predict', 256) < 300:
            recommendations['num_predict'] = 300

    return recommendations

def ensure_model_settings_exists(service, model_info):
    try:
        model_name = model_info.get('name') if isinstance(model_info, dict) else str(model_info)
        with service._model_settings_lock:
            if not service._model_settings:
                service._model_settings = load_model_settings(service) or {}
            if model_name in service._model_settings:
                return 'exists'
        recommended = recommend_settings_for_model(service, model_info)
        entry = {
            'settings': recommended,
            'source': 'recommended',
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        with service._model_settings_lock:
            service._model_settings[model_name] = entry
            write_model_settings_file(service, service._model_settings)
        return 'created'
    except Exception as e:
        service.logger.exception(f"Error ensuring model settings exists for {model_info}: {e}")
        return 'error'

def get_model_settings_entry(service, model_name):
    try:
        with service._model_settings_lock:
            if not service._model_settings:
                service._model_settings = load_model_settings(service) or {}
        if model_name in service._model_settings:
            return service._model_settings[model_name]
        model_info = service.get_model_info_cached(model_name) or {'name': model_name}
        recommended = recommend_settings_for_model(service, model_info)
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
        model_info = service.get_model_info_cached(model_name) or {'name': model_name}
        recommended = recommend_settings_for_model(service, model_info)
        return {
            'settings': recommended,
            'source': 'recommended',
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        service.logger.exception(f"Error getting model settings with fallback for {model_name}: {e}")
        return None

def save_model_settings_entry(service, model_name, settings, source='user'):
    try:
        if not isinstance(settings, dict):
            return False
        template = get_default_settings_template()
        clean = {}
        for k, default_val in template.items():
            if k in settings:
                clean[k] = normalize_setting_value(k, settings[k], default_val)
            else:
                clean[k] = default_val
        entry = {
            'settings': clean,
            'source': source,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        with service._model_settings_lock:
            if not service._model_settings:
                service._model_settings = load_model_settings(service) or {}
            service._model_settings[model_name] = entry
            write_model_settings_file(service, service._model_settings)
        return True
    except Exception as e:
        service.logger.exception(f"Error saving model settings for {model_name}: {e}")
        return False

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
