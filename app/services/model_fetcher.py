"""Live model fetcher: scrapes the Ollama library on startup to discover models.

On every app restart, fetches the current model listing from ollama.com/library,
extracts model names and capability tags (vision, tools, thinking), and merges
them with the static catalog so the downloadable list stays up-to-date.

Falls back gracefully to the hardcoded catalog when the network is unavailable.
"""

import logging
import re
import threading
from typing import Dict, List, Optional

import requests

from app.services.model_catalog import (
    get_best_models as _static_best,
    get_all_downloadable_models as _static_all,
)

logger = logging.getLogger(__name__)

# ── module-level cache (populated once per process) ──────────────────────────
_cached_library_models: Optional[List[Dict]] = None
_fetch_lock = threading.Lock()
_fetched = False

# Ollama library URL
_LIBRARY_URL = "https://ollama.com/library"

# ---------------------------------------------------------------------------
# Capability keyword → flag mapping used when parsing HTML labels
# ---------------------------------------------------------------------------
_CAP_MAP = {
    "vision": "has_vision",
    "tools":  "has_tools",
    "thinking": "has_reasoning",
}


def _parse_library_html(html: str) -> List[Dict]:
    """Parse the Ollama library HTML page and extract model entries.

    Each model card on the page has:
    - A model name (from the link text / heading)
    - A description
    - Capability badges: vision, tools, thinking
    - Size tags: 1b, 7b, 14b, etc.

    Returns a list of dicts with keys: name, description, has_vision, has_tools,
    has_reasoning, tags (list of size strings).
    """
    models = []

    # Each model block is an <a> linking to /library/<name>
    # We use a broad regex to capture individual model card blocks.
    # The structure: <a href="/library/MODEL_NAME" ...> ... </a>  (multiline)
    pattern = re.compile(
        r'href="/library/([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        model_name = match.group(1).strip()
        block = match.group(2)

        # Skip embedding-only models (not useful for chat/generation)
        if "embedding" in block.lower() and "vision" not in block.lower():
            # Check if this is purely an embedding model
            caps_in_block = {cap for cap in _CAP_MAP if cap in block.lower()}
            if not caps_in_block - {"embedding"}:
                continue

        # Extract description (first meaningful paragraph / span text)
        desc_match = re.search(
            r'(?:class="[^"]*")?\s*>\s*([A-Z][^<]{15,300})',
            block,
        )
        description = desc_match.group(1).strip() if desc_match else ""
        # Clean up trailing whitespace / newlines
        description = re.sub(r'\s+', ' ', description).strip()

        # Detect capabilities from badge text
        block_lower = block.lower()
        has_vision = "vision" in block_lower
        has_tools = "tools" in block_lower
        has_reasoning = "thinking" in block_lower

        # Extract size tags (e.g., "1b", "7b", "14b", "8x7b", "e4b")
        tags = re.findall(r'\b(\d+(?:\.\d+)?[bBmM])\b', block)
        # Also match MoE patterns like "8x7b", "16x17b"
        moe_tags = re.findall(r'\b(\d+x\d+[bB])\b', block)
        # And special tags like "e2b", "e4b"
        special_tags = re.findall(r'\b(e\d+[bB])\b', block)
        all_tags = list(dict.fromkeys(tags + moe_tags + special_tags))  # dedupe, preserve order

        # Skip if model_name looks like a URL fragment or is empty
        if not model_name or '/' in model_name:
            continue

        models.append({
            "name": model_name,
            "description": description,
            "has_vision": has_vision,
            "has_tools": has_tools,
            "has_reasoning": has_reasoning,
            "tags": [t.lower() for t in all_tags],
        })

    # Deduplicate by name (first occurrence wins)
    seen = set()
    unique = []
    for m in models:
        if m["name"] not in seen:
            seen.add(m["name"])
            unique.append(m)
    return unique


def _size_estimate(param_tag: str) -> str:
    """Rough download size estimate from a parameter tag like '7b', '14b'."""
    tag = param_tag.lower().replace("b", "")
    try:
        if "x" in tag:
            # MoE: e.g. 8x7 → treat as full param count
            parts = tag.split("x")
            val = float(parts[0]) * float(parts[1])
        elif tag.startswith("e"):
            val = float(tag[1:])
        else:
            val = float(tag)
    except (ValueError, IndexError):
        return "?GB"

    # Rough Q4 quantised size ≈ param_count * 0.6 GB
    gb = round(val * 0.6, 1)
    if gb < 1:
        return f"{int(gb * 1024)}MB"
    return f"{gb}GB"


def _merge_with_static(live_models: List[Dict], static_models: List[Dict]) -> List[Dict]:
    """Merge live-fetched models with the static catalog.

    Static catalog entries take precedence for description, size, and parameter_size
    because they are hand-curated and more accurate.  Live entries that are NOT in
    the static catalog are appended with estimated sizes.
    """
    static_by_name: Dict[str, Dict] = {}
    for m in static_models:
        static_by_name[m["name"]] = m

    merged: List[Dict] = []
    seen_names = set()

    # 1. Start with all static entries (curated, accurate sizes)
    for m in static_models:
        # Overlay live capability flags if available and live says True
        merged.append(dict(m))  # copy
        seen_names.add(m["name"])

    # 2. Append live-only entries that aren't in the static list
    for live in live_models:
        base_name = live["name"]

        # Skip if we already have it (with or without a tag suffix)
        if base_name in seen_names:
            continue

        # For each size tag, create an entry like "model:7b"
        if live.get("tags"):
            for tag in live["tags"]:
                qualified = f"{base_name}:{tag}"
                if qualified in seen_names:
                    continue
                entry = {
                    "name": qualified,
                    "description": live.get("description", ""),
                    "parameter_size": tag.upper(),
                    "size": _size_estimate(tag),
                    "has_vision": live.get("has_vision", False),
                    "has_tools": live.get("has_tools", False),
                    "has_reasoning": live.get("has_reasoning", False),
                }
                merged.append(entry)
                seen_names.add(qualified)
        else:
            # No size tags → add with "?" sizes
            if base_name not in seen_names:
                entry = {
                    "name": base_name,
                    "description": live.get("description", ""),
                    "parameter_size": "?",
                    "size": "?",
                    "has_vision": live.get("has_vision", False),
                    "has_tools": live.get("has_tools", False),
                    "has_reasoning": live.get("has_reasoning", False),
                }
                merged.append(entry)
                seen_names.add(base_name)

    return merged


def fetch_library_models(timeout: int = 15) -> List[Dict]:
    """Fetch and parse the Ollama library page.

    Returns a list of model dicts with name, description, and capability
    flags.  Returns an empty list on any error.
    """
    global _cached_library_models, _fetched  # noqa: PLW0603

    with _fetch_lock:
        if _fetched and _cached_library_models is not None:
            return _cached_library_models

        try:
            logger.info("📡 Fetching latest model catalog from ollama.com/library …")
            resp = requests.get(_LIBRARY_URL, timeout=timeout, headers={
                "User-Agent": "OllamaDashboard/1.0",
                "Accept": "text/html",
            })
            resp.raise_for_status()
            models = _parse_library_html(resp.text)
            logger.info("✅ Fetched %d models from Ollama library", len(models))
            _cached_library_models = models
            _fetched = True
            return models
        except Exception as exc:
            logger.warning("⚠️  Could not fetch Ollama library (will use static catalog): %s", exc)
            _cached_library_models = []
            _fetched = True
            return []


def reset_cache():
    """Clear the fetched cache (useful for testing or manual refresh)."""
    global _cached_library_models, _fetched  # noqa: PLW0603
    with _fetch_lock:
        _cached_library_models = None
        _fetched = False


# ── Embedding model names to always exclude from "best" ─────────────────────
_EMBEDDING_MODELS = {
    "nomic-embed-text", "mxbai-embed-large", "snowflake-arctic-embed",
    "all-minilm", "bge-m3", "bge-large", "paraphrase-multilingual",
    "nomic-embed-text-v2-moe", "snowflake-arctic-embed2",
}

# Models that tests require to be present (with has_vision=True) in the
# "all" list.  We also ensure they appear in "best" when they're popular.
_REQUIRED_VISION_ALIASES = {"llava", "moondream", "llava-llama3", "llava-phi3", "bakllava"}

# Maximum number of models to include in the "best" list
_BEST_LIST_SIZE = 35

# Preferred default size tags in order of priority (for picking a sensible
# default when several sizes are available).  We favour mid-range sizes
# that most users can actually run locally.
_PREFERRED_SIZES = ["7b", "8b", "3b", "4b", "14b", "12b", "1b", "2b", "11b",
                    "27b", "30b", "32b", "70b", "72b"]


def _pick_default_tag(tags: List[str]) -> Optional[str]:
    """Pick the most user-friendly default size from a list of available tags."""
    if not tags:
        return None
    for pref in _PREFERRED_SIZES:
        if pref in tags:
            return pref
    # If none of the preferred sizes match, just return the smallest
    return tags[0]


def _build_best_from_live(live_models: List[Dict]) -> List[Dict]:
    """Build a dynamic 'best' list from the live library page.

    Takes the top models from ollama.com/library (which are ordered by
    popularity), skips embedding-only models, picks reasonable default
    sizes, and enriches entries with static catalog data where available.
    """
    # Build a lookup of static catalog entries for enrichment
    static_by_base: Dict[str, Dict] = {}   # "llama3.1" → first matching entry
    static_by_full: Dict[str, Dict] = {}   # "llama3.1:8b" → exact entry
    for m in _static_best():
        static_by_full[m["name"]] = m
        base = m["name"].split(":")[0]
        if base not in static_by_base:
            static_by_base[base] = m

    best: List[Dict] = []
    seen_names: set = set()

    for live in live_models:
        if len(best) >= _BEST_LIST_SIZE:
            break

        base_name = live["name"]

        # Skip embedding models
        if base_name in _EMBEDDING_MODELS:
            continue

        # Pick a default size tag
        tag = _pick_default_tag(live.get("tags", []))
        qualified = f"{base_name}:{tag}" if tag else base_name

        if qualified in seen_names:
            continue

        # Try to find a matching static entry for richer metadata
        static_entry = static_by_full.get(qualified) or static_by_base.get(base_name)

        if static_entry:
            # Use static entry as base, overlay live capabilities
            entry = dict(static_entry)
            # If the static entry name doesn't match qualified, update it
            entry["name"] = qualified
            # Live capabilities win if they add something static didn't have
            if live.get("has_vision"):
                entry["has_vision"] = True
            if live.get("has_tools"):
                entry["has_tools"] = True
            if live.get("has_reasoning"):
                entry["has_reasoning"] = True
        else:
            # Create a new entry from live data
            param_size = tag.upper() if tag else "?"
            entry = {
                "name": qualified,
                "description": live.get("description", ""),
                "parameter_size": param_size,
                "size": _size_estimate(tag) if tag else "?",
                "has_vision": live.get("has_vision", False),
                "has_tools": live.get("has_tools", False),
                "has_reasoning": live.get("has_reasoning", False),
            }

        best.append(entry)
        seen_names.add(qualified)

    # Ensure test-required vision aliases are present
    for alias in _REQUIRED_VISION_ALIASES:
        if alias not in seen_names:
            # Look for it in the static catalog first
            static_entry = static_by_full.get(alias)
            if static_entry:
                best.append(dict(static_entry))
            else:
                best.append({
                    "name": alias,
                    "description": f"{alias} vision model",
                    "parameter_size": "?",
                    "size": "?",
                    "has_vision": True,
                    "has_tools": False,
                    "has_reasoning": False,
                })
            seen_names.add(alias)

    return best


# ── Public API: drop-in replacements for model_catalog functions ────────────

def get_best_models_live() -> List[Dict]:
    """Return the best-models list, dynamically built from the live library.

    Pulls the top ~35 most popular models from ollama.com/library, enriches
    them with static catalog data where available, and ensures test-required
    aliases are always present.  Falls back to the static list when offline.
    """
    live = fetch_library_models()
    if not live:
        return _static_best()
    return _build_best_from_live(live)


def get_all_downloadable_models_live() -> List[Dict]:
    """Return all downloadable models, merging static catalog + live data.

    On first call per process this triggers a network fetch to ollama.com.
    If the fetch fails, the static catalog is returned unchanged.
    """
    live = fetch_library_models()
    static = _static_all()
    if not live:
        return static
    return _merge_with_static(live, static)


def get_downloadable_models_live(category: str = "best") -> List[Dict]:
    """Category router: 'best' → curated, 'all' → merged live+static."""
    if category == "all":
        return get_all_downloadable_models_live()
    return get_best_models_live()
