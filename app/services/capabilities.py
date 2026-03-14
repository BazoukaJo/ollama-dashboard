"""Capability detection helpers for Ollama models.

Separated from ollama.py to reduce file length. Keep heuristics identical
so tests relying on existing behavior continue to pass.

Accuracy / priority (highest first):
  1. Ollama API capabilities array (from /api/show or /api/tags) — definitive when present.
  2. Explicit bool flags (catalog, live fetcher) — used when API has no capabilities.
  3. Heuristics (name + families patterns) — used when API and explicit are missing; can be wrong.

Note: Ollama returns capabilities as list of strings (e.g. ["completion", "vision", "tools"]).
Reasoning/thinking is not in Ollama's capability list yet; we infer it from heuristics or catalog.

Default API→flags mapping is loaded from model_capability_defaults.json when present.
"""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to default capability definition file (sourced from Ollama docs and community)
_CAPABILITY_DEFAULTS_PATH = Path(__file__).resolve().parent / "model_capability_defaults.json"
_capability_defaults_cache = None


def load_capability_defaults():
    """Load model_capability_defaults.json. Returns dict (empty if missing or invalid). Cached."""
    global _capability_defaults_cache
    if _capability_defaults_cache is not None:
        return _capability_defaults_cache
    try:
        if _CAPABILITY_DEFAULTS_PATH.is_file():
            with open(_CAPABILITY_DEFAULTS_PATH, encoding="utf-8") as f:
                _capability_defaults_cache = json.load(f)
            return _capability_defaults_cache
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Could not load capability defaults from %s: %s", _CAPABILITY_DEFAULTS_PATH, e)
    _capability_defaults_cache = {}
    return _capability_defaults_cache

# Vision model name patterns
_VISION_PATTERNS = [
    r'llava', r'bakllava', r'moondream', r'qwen.*vl', r'cogvlm', r'yi.*vl',
    r'deepseek.*vl', r'paligemma', r'fuyu', r'idefics',
    r'llava.*llama3', r'llava.*phi3', r'llava.*mistral',
    r'.*vl\b', r'.*vision\b', r'.*multimodal\b',
    r'qwen2.*vl', r'qwen2\.5.*vl', r'qwen3.*vl'
]

# Tool-capable model patterns
_TOOL_PATTERNS = [
    r'llama3\.[1-9]', r'llama.*3\.[1-9]',
    r'mistral', r'mixtral', r'mistral.*large',
    r'qwen2\.5', r'qwen3', r'qwen.*2\.5', r'qwen.*3',
    r'command.*r',
    r'firefunction', r'granite3', r'hermes3', r'nemotron',
    r'aya', r'phi.*3\.5', r'phi.*4',
    r'devstral'
]

# Exclusions for tool patterns (older / unsupported variants)
# Note: mistral:7b v0.3+ has tool support; do not exclude by size.
_TOOL_EXCLUDE_PATTERNS = [
    r'llama3\.0', r'llama2',
    r'qwen2\.0', r'qwen.*2\.0',
    r'hermes2', r'hermes.*2', r'qwen.*1\.*',
]

# Reasoning model patterns
_REASONING_PATTERNS = [
    r'deepseek.*r1', r'deepseek.*reasoning',
    r'qwq', r'qwen.*qwq', r'qwen.*reasoning',
    r'o1', r'o2', r'o3',
    r'marco.*o1', r'k0.*math', r'.*reasoning', r'.*think',
    r'.*cot', r'.*chain.*thought'
]

_REASONING_INDICATORS = ['math', 'reasoning', 'thinking', 'think', 'cognitive']
_TOOL_FUNCTION_INDICATORS = ['tools', 'function', 'function-calling', 'tool-use']
_VISION_FAMILY_INDICATORS = ['clip', 'projector', 'vision', 'multimodal', 'vl', 'llava', 'siglip']


def detect_capabilities(model_name: str, families) -> dict:
    """Return capability flags for model name + families.

    Returns True when supported, None when undefined (heuristics didn't match).
    Use Ollama API capabilities or explicit catalog flags for False (known not supported).
    """
    capabilities = {
        'has_vision': None,
        'has_tools': None,
        'has_reasoning': None
    }

    name_lower = (model_name or '').lower()
    families = families or []

    # Tokenize for reasoning heuristics
    tokens = re.split(r'[\-_:\.]', name_lower)
    token_set = set(tokens)

    # Vision detection
    if any(re.search(p, name_lower, re.IGNORECASE) for p in _VISION_PATTERNS):
        capabilities['has_vision'] = True

    if isinstance(families, list):
        for fam in families:
            fam_l = str(fam).lower()
            if any(x in fam_l for x in _VISION_FAMILY_INDICATORS):
                capabilities['has_vision'] = True
                break
    elif isinstance(families, str):
        fam_l = families.lower()
        if any(x in fam_l for x in _VISION_FAMILY_INDICATORS):
            capabilities['has_vision'] = True

    # Tool detection
    if any(re.search(p, name_lower, re.IGNORECASE) for p in _TOOL_EXCLUDE_PATTERNS):
        capabilities['has_tools'] = False  # Known not supported (e.g. llama3.0)
    elif (any(re.search(p, name_lower, re.IGNORECASE) for p in _TOOL_PATTERNS) or
          any(ind in name_lower for ind in _TOOL_FUNCTION_INDICATORS)):
        capabilities['has_tools'] = True

    # Reasoning detection
    if any(re.search(p, name_lower, re.IGNORECASE) for p in _REASONING_PATTERNS):
        capabilities['has_reasoning'] = True

    if ('r1' in token_set or 'r-1' in token_set) and not any(t.startswith('v1') for t in token_set):
        reasoning_bases = ['deepseek', 'llama', 'qwen', 'phi', 'mixtral', 'marco', 'qwq']
        if any(base in name_lower for base in reasoning_bases):
            capabilities['has_reasoning'] = True

    if any(ind in name_lower for ind in _REASONING_INDICATORS):
        capabilities['has_reasoning'] = True

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Capabilities for '{model_name}': {capabilities}")
        logger.debug(f"Tokens: {tokens}; Families: {families}")

    return capabilities


def _caps_from_ollama_api(caps_list: list) -> dict | None:
    """Map Ollama API capabilities array to has_vision, has_tools, has_reasoning.
    Returns dict with True/False when we have definitive API data, else None.
    Uses api_to_flags from model_capability_defaults.json when available.
    """
    if not caps_list or not isinstance(caps_list, list):
        return None
    caps_lower = [str(c).lower().strip() for c in caps_list]
    defaults = load_capability_defaults()
    api_to_flags = (defaults or {}).get("api_to_flags") or {}
    vision_aliases = api_to_flags.get("has_vision") or ["vision", "image", "multimodal"]
    tools_aliases = api_to_flags.get("has_tools") or [
        "tools", "tool", "function", "function-calling", "tool-use"
    ]
    reasoning_aliases = api_to_flags.get("has_reasoning") or ["reasoning", "thinking", "think"]
    return {
        "has_vision": any(x in caps_lower for x in vision_aliases),
        "has_tools": any(x in caps_lower for x in tools_aliases),
        "has_reasoning": any(x in caps_lower for x in reasoning_aliases),
    }


def ensure_capability_flags(model: dict, prefer_heuristics_on_conflict: bool = False) -> dict:
    """Normalize capability flags: True (supported), False (known not supported), None (undefined).

    Priority for each flag (first wins): (1) Ollama API capabilities array, (2) explicit bool on model,
    (3) heuristics from name/families. API is always authoritative when present.

    - Green: True = feature supported
    - Grey: False = known to be not functional
    - Yellow: None = status undefined
    """
    try:
        name = model.get('name', '')
        details = model.get('details', {}) or {}
        families = details.get('families', []) or []
        caps_list = model.get('capabilities') or details.get('capabilities')

        # 1. Ollama API capabilities (definitive): True or False
        api_caps = _caps_from_ollama_api(caps_list) if caps_list else None

        # 2. Explicit catalog/source flags (definitive when bool)
        def get_flag(key: str):
            val = model.get(key)
            if api_caps is not None and key in api_caps:
                return api_caps[key]
            if isinstance(val, bool):
                return val
            if prefer_heuristics_on_conflict or val is None or not isinstance(val, bool):
                detected = detect_capabilities(name, families).get(key)
                return detected  # True or None
            return bool(val)

        model['has_vision'] = get_flag('has_vision')
        model['has_tools'] = get_flag('has_tools')
        model['has_reasoning'] = get_flag('has_reasoning')
    except Exception:
        model.setdefault('has_vision', None)
        model.setdefault('has_tools', None)
        model.setdefault('has_reasoning', None)
    return model
