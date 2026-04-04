"""Model formatting helpers extracted from OllamaService."""
from app.services.capabilities import ensure_capability_flags


def format_context_length(ctx):
    """Format context length from provider (number or string) for display (e.g. 128000 -> '128K')."""
    if ctx is None:
        return None
    if isinstance(ctx, str) and ctx.strip():
        return ctx.strip()
    try:
        n = int(ctx)
    except (TypeError, ValueError):
        return str(ctx) if ctx else None
    if n <= 0:
        return None
    if n >= 1_000_000:
        return f"{n // 1_000_000}M"
    if n >= 1000:
        return f"{n // 1000}K"
    return str(n)


def _raw_loaded_context_from_ps(model):
    """Context window allocated for the loaded process (/api/ps): options.num_ctx or context_length."""
    if not isinstance(model, dict):
        return None
    opts = model.get("options")
    if isinstance(opts, dict):
        v = opts.get("num_ctx")
        if v is not None:
            return v
    v = model.get("context_length")
    if v is not None:
        return v
    details = model.get("details") or {}
    return details.get("context_length")


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


def _coerce_context_int(value):
    """Parse a context length to a positive int (handles 8192, '8K', '128K', etc.)."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 else None
    if isinstance(value, str):
        s = value.strip().upper().replace(",", "").replace(" ", "")
        if not s:
            return None
        mult = 1
        if s.endswith("M"):
            mult = 1_000_000
            s = s[:-1]
        elif s.endswith("K"):
            mult = 1000
            s = s[:-1]
        try:
            n = int(float(s) * mult)
            return n if n > 0 else None
        except ValueError:
            return None
    return None


def context_length_as_int(entry):
    """Numeric context window for settings logic (prefers raw API fields over display strings)."""
    if not isinstance(entry, dict):
        return None
    details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    for candidate in (details.get("context_length"), entry.get("context_length")):
        n = _coerce_context_int(candidate)
        if n is not None:
            return n
    raw = _extract_context_length(entry)
    n = _coerce_context_int(raw)
    if n is not None:
        return n
    mi = entry.get("model_info")
    if isinstance(mi, dict):
        for key, val in mi.items():
            kl = key.lower()
            if "context" in kl and "length" in kl:
                n = _coerce_context_int(val)
                if n is not None:
                    return n
    return None


def request_context_length_from_settings(service, model_name):
    """Dashboard num_ctx (formatted) used when attaching options to generate/chat requests."""
    if not model_name or service is None:
        return None
    try:
        data = service.get_model_settings_with_fallback(str(model_name))
        if not isinstance(data, dict):
            return None
        settings = data.get("settings") or {}
        nctx = settings.get("num_ctx")
        if nctx is None:
            return None
        return format_context_length(nctx)
    except Exception:
        return None


def attach_request_context_to_model(service, model_dict):
    if not isinstance(model_dict, dict):
        return
    name = model_dict.get("name")
    if not name:
        return
    model_dict["request_context_length"] = request_context_length_from_settings(
        service, name
    )


def format_token_count_display(total):
    """Format a token count for model cards (thousands separators)."""
    if total is None:
        return None
    try:
        n = int(total)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return f"{n:,}"


def attach_last_token_usage_to_model(service, model_dict):
    """Attach last dashboard /api/generate token total (prompt + completion) for display."""
    if not isinstance(model_dict, dict):
        return
    name = model_dict.get("name")
    if not name or service is None:
        return
    getter = getattr(service, "get_last_generate_token_total", None)
    if not callable(getter):
        return
    total = getter(name)
    disp = format_token_count_display(total)
    if disp:
        model_dict["context_tokens_used_total"] = total
        model_dict["context_tokens_used_display"] = disp


def normalize_available_model_entry(service, entry, prefer_heuristics_on_conflict=False):
    if not isinstance(entry, dict):
        return {'name': str(entry), 'has_vision': False, 'has_tools': False, 'has_reasoning': False}
    raw_ctx = _extract_context_length(entry)
    model = {
        'name': entry.get('name', 'unknown'),
        'size': entry.get('size'),
        'modified_at': entry.get('modified_at'),
        'details': entry.get('details') if entry.get('details') is not None else {},
        'tags': entry.get('tags'),
        'digest': entry.get('digest'),
        'context_length': format_context_length(raw_ctx) if raw_ctx is not None else None,
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
    attach_request_context_to_model(service, model)
    attach_last_token_usage_to_model(service, model)
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
            'context_length': format_context_length(_extract_context_length(model)) if isinstance(model, dict) else None,
        }

        if isinstance(model, dict):
            raw_loaded = _raw_loaded_context_from_ps(model)
            entry['loaded_context_length'] = (
                format_context_length(raw_loaded) if raw_loaded is not None else None
            )
        else:
            entry['loaded_context_length'] = None

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
        attach_request_context_to_model(service, entry)
        attach_last_token_usage_to_model(service, entry)
        return entry
    except Exception:
        return {'name': str(model), 'running': False, 'has_vision': False, 'has_tools': False, 'has_reasoning': False}
