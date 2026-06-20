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

# Mixture-of-Experts model name patterns (display-only flag; Ollama routes experts internally).
# Matches mixtral, NxMb notation (8x7b/8x22b), total-active notation (30b-a3b), and known MoE families.
_MOE_PATTERNS = [
    r'mixtral', r'\d+x\d+b', r'\bmoe\b', r'-moe', r'\d+b-a\d+b',
    r'gpt-oss', r'deepseek-?v[23]', r'llama4', r'dbrx', r'jamba', r'qwen3-?moe',
    r'granite.*moe', r'phi.*moe', r'grok',
]


def _match_family_defaults(name_lower: str) -> dict:
    """Capability flags from model_capability_defaults.json family lists (heuristic fallback).

    Returns only True/None per flag (never False) — used to fill gaps the regex heuristics miss
    (e.g. gemma3/minicpm-v vision, gpt-oss tools) without contradicting definitive False signals.
    """
    out = {'has_vision': None, 'has_tools': None, 'has_reasoning': None, 'has_moe': None}
    fam = (load_capability_defaults() or {}).get('family_defaults') or {}
    base = name_lower.split(':', 1)[0].split('/')[-1]
    if not base:
        return out

    def _matches(families) -> bool:
        for f in families or []:
            fl = str(f).lower().strip()
            if fl and (base == fl or base.startswith(fl)):
                return True
        return False

    if _matches(fam.get('vision_families')):
        out['has_vision'] = True
    if _matches(fam.get('tools_families')):
        out['has_tools'] = True
    if _matches(fam.get('reasoning_families')):
        out['has_reasoning'] = True
    if _matches(fam.get('moe_families')):
        out['has_moe'] = True
    return out


def detect_capabilities(model_name: str, families) -> dict:
    """Return capability flags for model name + families.

    Returns True when supported, None when undefined (heuristics didn't match).
    Use Ollama API capabilities or explicit catalog flags for False (known not supported).
    """
    capabilities = {
        'has_vision': None,
        'has_tools': None,
        'has_reasoning': None,
        'has_moe': None,
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

    # Mixture-of-Experts detection (display flag).
    if any(re.search(p, name_lower, re.IGNORECASE) for p in _MOE_PATTERNS):
        capabilities['has_moe'] = True
    if isinstance(families, list) and any('moe' in str(f).lower() for f in families):
        capabilities['has_moe'] = True

    # Fill remaining gaps from curated family lists (only sets True, never overrides False).
    family_caps = _match_family_defaults(name_lower)
    for key in ('has_vision', 'has_tools', 'has_reasoning', 'has_moe'):
        if capabilities.get(key) is None and family_caps.get(key) is True:
            capabilities[key] = True

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
    has_reasoning_alias = any(x in caps_lower for x in reasoning_aliases)
    return {
        "has_vision": any(x in caps_lower for x in vision_aliases),
        "has_tools": any(x in caps_lower for x in tools_aliases),
        # Ollama's capabilities array does not (yet) advertise reasoning/thinking, so absence is
        # NOT proof of "no reasoning". Only report True when an alias is actually present;
        # otherwise leave None so name/family heuristics and the catalog can decide.
        "has_reasoning": True if has_reasoning_alias else None,
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

        # 1. Ollama API capabilities (definitive only per-key when not None)
        api_caps = _caps_from_ollama_api(caps_list) if caps_list else None
        # Heuristics computed once (also supplies has_moe, which the API never reports).
        heuristics = detect_capabilities(name, families)

        # Priority per flag: API (when it gives a definitive non-None value) > explicit bool > heuristics.
        def get_flag(key: str):
            if api_caps is not None and api_caps.get(key) is not None:
                return api_caps[key]
            val = model.get(key)
            if isinstance(val, bool) and not prefer_heuristics_on_conflict:
                return val
            return heuristics.get(key)

        model['has_vision'] = get_flag('has_vision')
        model['has_tools'] = get_flag('has_tools')
        model['has_reasoning'] = get_flag('has_reasoning')
        model['has_moe'] = get_flag('has_moe')
    except (AttributeError, KeyError, TypeError, ValueError):
        model.setdefault('has_vision', None)
        model.setdefault('has_tools', None)
        model.setdefault('has_reasoning', None)
        model.setdefault('has_moe', None)
    return model
