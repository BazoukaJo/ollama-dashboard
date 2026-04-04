"""Compare installed Ollama to latest GitHub release (e.g. each full page load on GET /)."""
# pylint: disable=broad-exception-caught
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

GITHUB_LATEST = "https://api.github.com/repos/ollama/ollama/releases/latest"
REQUEST_TIMEOUT = 12
USER_AGENT = "ollama-dashboard-update-check"


def _version_tuple(ver: str) -> Tuple[int, ...]:
    """Parse a version string into a tuple of integers for comparison (best-effort)."""
    s = (ver or "").strip().lstrip("vV")
    parts = re.findall(r"\d+", s)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts[:8])


def _compare_versions(a: str, b: str) -> int:
    """Return 1 if a > b, -1 if a < b, 0 if equal (by numeric segments)."""
    ta, tb = _version_tuple(a), _version_tuple(b)
    n = max(len(ta), len(tb))
    pa = ta + (0,) * (n - len(ta))
    pb = tb + (0,) * (n - len(tb))
    if pa > pb:
        return 1
    if pa < pb:
        return -1
    return 0


def fetch_latest_ollama_tag(session: Optional[requests.Session] = None) -> Optional[str]:
    """Return latest release tag_name from GitHub (e.g. v0.5.4), or None on failure."""
    sess = session or requests.Session()
    try:
        resp = sess.get(
            GITHUB_LATEST,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name")
        if isinstance(tag, str) and tag.strip():
            return tag.strip()
    except Exception as exc:
        logger.info("Could not fetch latest Ollama release from GitHub: %s", exc)
    return None


def run_startup_ollama_update_check(
    ollama_service: Any,
    *,
    refresh_installed_version: bool = False,
) -> Dict[str, Any]:
    """Compare running Ollama version to latest GitHub release.

    Args:
        refresh_installed_version: If True, bypass TTL cache and hit /api/version again
            (use on each dashboard page load so reload reflects upgrades).

    Returns:
        update_available: bool — True only when latest is strictly newer than installed
        current_version: str
        latest_version: str or None
    """
    current = "Unknown"
    try:
        if ollama_service is not None and hasattr(ollama_service, "get_ollama_version"):
            getter = ollama_service.get_ollama_version
            if refresh_installed_version:
                current = getter(force_refresh=True) or "Unknown"
            else:
                current = getter() or "Unknown"
    except Exception as exc:
        logger.debug("get_ollama_version in update check: %s", exc)
        current = "Unknown"

    if not current or current == "Unknown":
        return {
            "update_available": False,
            "current_version": current,
            "latest_version": None,
        }

    session = None
    try:
        if ollama_service is not None and hasattr(ollama_service, "_session"):
            session = getattr(ollama_service, "_session", None)
    except Exception:
        session = None

    latest = fetch_latest_ollama_tag(session)
    if not latest:
        return {
            "update_available": False,
            "current_version": current,
            "latest_version": None,
        }

    newer = _compare_versions(latest, current) > 0
    if newer:
        logger.info("Ollama update available: current=%s latest=%s", current, latest)
    else:
        logger.debug("Ollama update check: current=%s latest=%s available=%s", current, latest, newer)
    return {
        "update_available": newer,
        "current_version": current,
        "latest_version": latest,
    }
