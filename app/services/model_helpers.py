"""Model formatting helpers extracted from OllamaService."""
from app.services.capabilities import ensure_capability_flags


def _extract_context_length(entry):
    """Extract context_length from entry (top-level, details, or model_info)."""
    if not isinstance(entry, dict):
        return None
    ctx = entry.get('context_length')
    if ctx is not None:
        return ctx
    details = entry.get('details') or {}
    ctx = details.get('context_length')
    if ctx is not None:
        return ctx
    model_info = entry.get('model_info') or {}
    for key, val in model_info.items():
        if 'context_length' in key.lower() and val is not None:
            return val
    return None


def normalize_available_model_entry(service, entry, prefer_heuristics_on_conflict=False):
    if not isinstance(entry, dict):
        return {'name': str(entry), 'has_vision': False, 'has_tools': False, 'has_reasoning': False}
    model = {
        'name': entry.get('name', 'unknown'),
        'size': entry.get('size'),
        'modified_at': entry.get('modified_at'),
        'details': entry.get('details') if entry.get('details') is not None else {},
        'tags': entry.get('tags'),
        'digest': entry.get('digest'),
        'context_length': _extract_context_length(entry),
    }
    if isinstance(model.get('size'), (int, float)):
        try:
            model['formatted_size'] = service.format_size(model['size'])
        except Exception:
            pass
    try:
        model = ensure_capability_flags(model, prefer_heuristics_on_conflict=prefer_heuristics_on_conflict)
    except (ValueError, KeyError, TypeError):
        model.setdefault('has_vision', False)
        model.setdefault('has_tools', False)
        model.setdefault('has_reasoning', False)
    return model

def format_running_model_entry(service, model, include_has_custom_settings=False, prefer_heuristics_on_conflict=False):
    try:
        if isinstance(model, dict) and 'size' in model and 'formatted_size' not in model:
            size_val = model.get('size')
            if isinstance(size_val, (int, float)):
                model['formatted_size'] = service.format_size(size_val)
        entry = {
            'name': model.get('name', 'unknown') if isinstance(model, dict) else str(model),
            'size': model.get('size') if isinstance(model, dict) else None,
            'details': model.get('details') if (isinstance(model, dict) and model.get('details') is not None) else {},
            'modified_at': model.get('modified_at') if isinstance(model, dict) else None,
            'expires_at': model.get('expires_at') if isinstance(model, dict) else None,
            'formatted_size': model.get('formatted_size') if isinstance(model, dict) else None,
            'running': model.get('running', False) if isinstance(model, dict) else False,
            'last_request': model.get('last_request') if isinstance(model, dict) else None,
            'age': model.get('age') if isinstance(model, dict) else None,
            'keep_alive': model.get('keep_alive') if isinstance(model, dict) else None,
            'session': model.get('session') if isinstance(model, dict) else None,
            'digest': model.get('digest') if isinstance(model, dict) else None,
            'tags': model.get('tags') if isinstance(model, dict) else None,
            'size_vram': model.get('size_vram') if isinstance(model, dict) else None,
            'context_length': _extract_context_length(model) if isinstance(model, dict) else None,
        }

        # Format VRAM size if present
        if entry.get('size_vram') is not None:
            try:
                entry['formatted_size_vram'] = service.format_size(entry['size_vram'])
            except Exception:
                entry['formatted_size_vram'] = str(entry['size_vram'])

        try:
            entry = ensure_capability_flags(entry, prefer_heuristics_on_conflict=prefer_heuristics_on_conflict)
        except Exception:
            entry.setdefault('has_vision', False)
            entry.setdefault('has_tools', False)
            entry.setdefault('has_reasoning', False)
        if include_has_custom_settings:
            try:
                ms = service.get_model_settings(entry['name']) or {}
                entry['has_custom_settings'] = bool(ms.get('source') == 'user')
            except Exception:
                entry['has_custom_settings'] = False
        return entry
    except Exception:
        return {'name': str(model), 'running': False, 'has_vision': False, 'has_tools': False, 'has_reasoning': False}
