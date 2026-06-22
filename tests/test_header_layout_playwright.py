"""
Header layout regression tests — geometry at multiple viewport widths.

Requires: pip install playwright && playwright install chromium

Run: pytest tests/test_header_layout_playwright.py -v
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import time

import pytest
import requests

PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None
PYTEST_PLAYWRIGHT = importlib.util.find_spec("pytest_playwright") is not None

pytest_plugins = ["pytest_playwright"] if PYTEST_PLAYWRIGHT else []

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.skipif(
        not (PLAYWRIGHT_AVAILABLE and PYTEST_PLAYWRIGHT),
        reason="Playwright not installed (pip install pytest-playwright && playwright install chromium)",
    ),
]

VIEWPORTS = [
    (390, 844, "phone"),
    (520, 844, "phone-wide"),
    (768, 1024, "tablet"),
    (992, 900, "tablet-wide"),
    (1200, 900, "desktop-narrow"),
    (1400, 900, "desktop"),
    (1800, 900, "desktop-wide"),
]

def _start_server():
    env = os.environ.copy()
    env.setdefault("FLASK_DEBUG", "0")
    proc = subprocess.Popen(
        ["python", "OllamaDashboard.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(40):
        try:
            if requests.get("http://127.0.0.1:5000/", timeout=3).status_code == 200:
                return proc
        except (requests.RequestException, OSError):
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("Flask server did not start for header layout tests")


@pytest.fixture(scope="module")
def server_process():
    proc = _start_server()
    yield proc
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()


@pytest.fixture(scope="module")
def browser_context():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=1,
        )
        yield context
        context.close()
        browser.close()


@pytest.fixture
def page(browser_context):
    pg = browser_context.new_page()
    yield pg
    pg.close()


@pytest.fixture(autouse=True)
def _mock_fetch(request):
    if "page" not in request.fixturenames:
        yield
        return
    page = request.getfixturevalue("page")
    page.add_init_script(
        """
        window.fetch = (url, opts) => Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, message: 'mock' }),
          text: () => Promise.resolve('{}'),
        });
        """
    )
    yield


def _box(page, selector: str) -> dict[str, float] | None:
    loc = page.locator(selector).first
    if loc.count() == 0:
        return None
    b = loc.bounding_box()
    if not b:
        return None
    return {
        "left": b["x"],
        "top": b["y"],
        "width": b["width"],
        "height": b["height"],
        "right": b["x"] + b["width"],
        "bottom": b["y"] + b["height"],
    }


def _assert_no_horizontal_overflow(page, label: str):
    metrics = page.evaluate(
        """() => {
          const zoom = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
          const clientW = document.documentElement.clientWidth;
          const scrollW = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth);
          const layoutViewportW = clientW / zoom;
          return { clientW, scrollW, zoom, layoutViewportW };
        }"""
    )
    assert metrics["scrollW"] <= metrics["layoutViewportW"] + 3, (
        f"{label}: horizontal overflow scrollWidth={metrics['scrollW']} "
        f"layoutViewport={metrics['layoutViewportW']} (zoom={metrics['zoom']})"
    )


def _assert_contains(outer: dict[str, float], inner: dict[str, float], pad: float, label: str):
    assert inner["left"] >= outer["left"] - pad, f"{label}: content left of panel border"
    assert inner["right"] <= outer["right"] + pad, f"{label}: content right of panel border"
    assert inner["top"] >= outer["top"] - pad, f"{label}: content above panel border"
    assert inner["bottom"] <= outer["bottom"] + pad, f"{label}: content below panel border"


@pytest.mark.parametrize("width,height,label", VIEWPORTS)
def test_header_layout_at_viewport(page, server_process, width, height, label):
    page.set_viewport_size({"width": width, "height": height})
    page.goto("http://127.0.0.1:5000/")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_selector(".dashboard-header-bar", timeout=10000)

    _assert_no_horizontal_overflow(page, label)

    bar = _box(page, ".dashboard-header-bar")
    theme = _box(page, "#themeToggleBtn")
    start = _box(page, ".dashboard-header-start")
    meta = _box(page, ".dashboard-header-meta-group")
    resources = _box(page, ".dashboard-header-resources-strip .compact-system-resources")

    assert bar is not None, f"{label}: header bar missing"
    assert theme is not None, f"{label}: theme toggle missing"
    assert start is not None, f"{label}: header start missing"
    assert meta is not None, f"{label}: meta group missing"

    banner_w = page.evaluate("() => document.querySelector('.dashboard-header-banner')?.clientWidth || 0")

    # Theme toggle stays top-right of the bar, not on a second row below content.
    assert theme["top"] <= bar["top"] + 8, f"{label}: theme toggle dropped below bar top"
    assert theme["right"] <= bar["right"] + 4, f"{label}: theme toggle outside bar right edge"
    assert theme["left"] > start["right"] - 20, f"{label}: theme overlaps Ollama controls"

    # Ollama service cluster: logo, health, and controls always share one row.
    lock = _box(page, ".dashboard-header-start-lock")
    toolbar = _box(page, ".dashboard-header-ollama-toolbar")
    assert lock is not None and toolbar is not None
    assert abs(lock["top"] - toolbar["top"]) < 12, (
        f"{label}: service buttons must stay on the same row as logo/health"
    )

    # Unified info panel holds two stacked rows (Ollama backend + API proxy).
    info_panel = _box(page, ".dashboard-header-info-panel")
    assert info_panel is not None, f"{label}: info panel missing"
    ollama_row = _box(page, ".dashboard-header-info-row--ollama")
    proxy_row = _box(page, ".dashboard-header-info-row--proxy")
    assert ollama_row is not None and proxy_row is not None
    assert ollama_row["top"] < proxy_row["top"] - 2, (
        f"{label}: Ollama row should sit above proxy row"
    )

    # Meta cluster sits on the same row as controls when the banner is wide enough (~48rem+).
    if banner_w >= 768:
        assert abs(start["top"] - meta["top"]) < 20, (
            f"{label}: meta group should share row with Ollama controls (banner={banner_w})"
        )
        full = page.locator(".dashboard-header-info-panel .dashboard-header-panel-full").first
        assert full.is_visible(), f"{label}: full info panel should show (banner={banner_w})"
        compact = page.locator(".dashboard-header-info-panel .dashboard-header-panel-compact").first
        assert not compact.is_visible(), f"{label}: compact strip hidden when banner wide"

    # Narrow banner: compact address strips (~42rem).
    if banner_w <= 672:
        assert page.locator(".dashboard-header-panel-compact").first.is_visible(), (
            f"{label}: compact strips when banner is narrow ({banner_w}px)"
        )
        assert not page.locator(
            ".dashboard-header-info-panel .dashboard-header-panel-full"
        ).first.is_visible()

    # Stacked layout: status drops below controls only below ~48rem.
    if 672 < banner_w < 768:
        assert page.locator(".dashboard-header-info-panel .dashboard-header-panel-full").first.is_visible()
        min_layout_w = page.evaluate(
            """() => {
              const density = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ui-density')) || 1;
              const visual = parseFloat(getComputedStyle(document.querySelector('.dashboard-header-meta-group'))
                .getPropertyValue('--hdr-meta-panel-min-visual')) || 12;
              return Math.floor((visual / density) * 16 * 0.92);
            }"""
        )
        info_layout_w = page.evaluate(
            "(s) => document.querySelector(s)?.offsetWidth || 0", ".dashboard-header-info-panel"
        )
        assert info_layout_w >= min_layout_w, (
            f"{label}: info panel below min width ({info_layout_w}px < {min_layout_w}px, banner={banner_w})"
        )
        assert info_panel["left"] >= bar["left"] - 6, (
            f"{label}: info panel clipped left (panel={info_panel['left']:.0f}, bar={bar['left']:.0f})"
        )
        assert info_panel["right"] <= bar["right"] + 6, (
            f"{label}: info panel clipped right (panel={info_panel['right']:.0f}, bar={bar['right']:.0f})"
        )
        start_bottom = start["top"] + start["height"]
        assert start["top"] < meta["top"] - 4 or start_bottom <= meta["top"] + 4, (
            f"{label}: meta group should sit below controls when banner={banner_w}"
        )

    # Medium-wide: same row as controls; panel stays inside the bar.
    if 768 <= banner_w < 1056:
        assert page.locator(".dashboard-header-info-panel .dashboard-header-panel-full").first.is_visible()
        min_layout_w = page.evaluate(
            """() => {
              const density = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ui-density')) || 1;
              const visual = parseFloat(getComputedStyle(document.querySelector('.dashboard-header-meta-group'))
                .getPropertyValue('--hdr-meta-panel-min-visual')) || 12;
              return Math.floor((visual / density) * 16 * 0.92);
            }"""
        )
        info_layout_w = page.evaluate(
            "(s) => document.querySelector(s)?.offsetWidth || 0", ".dashboard-header-info-panel"
        )
        assert info_layout_w >= min_layout_w, (
            f"{label}: info panel below min width ({info_layout_w}px < {min_layout_w}px, banner={banner_w})"
        )
        assert info_panel["left"] >= bar["left"] - 6, (
            f"{label}: info panel clipped left (panel={info_panel['left']:.0f}, bar={bar['left']:.0f})"
        )
        assert info_panel["right"] <= bar["right"] + 6, (
            f"{label}: info panel clipped right (panel={info_panel['right']:.0f}, bar={bar['right']:.0f})"
        )

    # Panel borders wrap their chips when full panel is visible.
    if page.locator(".dashboard-header-info-panel .dashboard-header-panel-full").first.is_visible():
        info_panel = _box(page, ".dashboard-header-info-panel")
        chip = _box(page, ".dashboard-header-info-row--ollama .dashboard-header-meta-chip")
        if info_panel and chip:
            _assert_contains(info_panel, chip, 6, f"{label} info panel")

        proxy_url = _box(page, "#apiProxyEndpoint")
        if info_panel and proxy_url:
            _assert_contains(info_panel, proxy_url, 6, f"{label} info panel proxy url")

        if page.locator("#apiProxyEndpoint").is_visible():
            ollama_host = _box(page, ".dashboard-header-info-row--ollama .dashboard-meta-host")
            proxy_badge = _box(page, "#apiProxyStatusBadge")
            proxy_connect = _box(page, ".dashboard-header-proxy-connect")
            if ollama_host and proxy_url:
                assert ollama_host["left"] <= proxy_url["left"] + 8, (
                    f"{label}: backend address should lead the Ollama row"
                )
            if proxy_url and proxy_badge:
                assert proxy_url["left"] <= proxy_badge["left"] + 8, (
                    f"{label}: proxy address should lead the proxy row"
                )
            if proxy_url and proxy_connect:
                assert proxy_connect["left"] >= proxy_badge["left"] - 4, (
                    f"{label}: Connect should sit after proxy status badge"
                )

    # Meta pair centered when stacked on row 2; never stretched to full bar width.
    if banner_w < 768:
        bar_cx = (bar["left"] + bar["right"]) / 2
        meta_cx = (meta["left"] + meta["right"]) / 2
        assert abs(bar_cx - meta_cx) < 48, (
            f"{label}: meta group should be centered (banner={banner_w})"
        )
        assert meta["width"] < bar["width"] * 0.92, (
            f"{label}: meta panels should not stretch to full bar width"
        )

    # System resources strip aligns with header content width (no extra gutter inside bar).
    if resources and bar:
        assert resources["left"] >= bar["left"] - 4, (
            f"{label}: resources strip hangs left of header bar"
        )
        assert resources["right"] <= bar["right"] + 4, (
            f"{label}: resources strip extends past header bar"
        )


def test_header_css_rules_present():
    """Static guard: header layout selectors must exist in styles.css."""
    from pathlib import Path

    css = (Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "styles.css").read_text(
        encoding="utf-8"
    )
    required = [
        ".dashboard-header-meta-group",
        ".dashboard-header-info-panel",
        ".dashboard-header-info-row",
        ".dashboard-header-row-label",
        ".dashboard-header-row-body",
        ".dashboard-header-panel-full",
        "grid-template-columns: subgrid",
        ".dashboard-header-panel-compact",
        "@container dash-hdr",
        "grid-template-columns: max-content",
        "justify-content: center",
    ]
    missing = [s for s in required if s not in css]
    assert not missing, f"Missing header CSS: {missing}"


def test_index_html_header_structure():
    """Template must expose meta-group + panel wrappers expected by CSS."""
    from unittest.mock import patch

    from app import create_app
    from app.routes import main

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    stats = {
        "cpu_percent": 0,
        "memory": {"percent": 0, "total": 0, "available": 0, "used": 0},
        "vram": {"percent": 0, "total": 0, "used": 0, "free": 0, "gpu_3d": 0},
        "disk": {"percent": 0},
    }
    with patch.object(main.ollama_service, "is_ollama_installed", return_value=True), patch(
        "app.routes.main.run_startup_ollama_update_check",
        return_value={"update_available": False, "current_version": "0.17.0"},
    ), patch.object(main.ollama_service, "get_running_models", return_value=[]), patch.object(
        main.ollama_service, "get_available_models", return_value=[]
    ), patch.object(
        main.ollama_service, "get_system_stats", return_value=stats
    ), patch.object(
        main.ollama_service, "get_ollama_version", return_value="0.17.0"
    ):
        html = client.get("/").get_data(as_text=True)

    for marker in (
        "dashboard-header-meta-group",
        "dashboard-header-info-panel",
        "dashboard-header-info-row--ollama",
        "dashboard-header-info-row--proxy",
        "dashboard-header-panel-full",
        "dashboard-header-panel-compact",
        "ollamaBackendStatusBadge",
        "dashboard-meta-host",
        "http://localhost:11434",
    ):
        assert marker in html, f"Missing in index.html: {marker}"

    assert "refresh-indicator" not in html
    assert 'id="refreshDashboardBtn"' not in html

    ollama_row_start = html.find("dashboard-header-info-row--ollama")
    proxy_row_start = html.find("dashboard-header-info-row--proxy", ollama_row_start)
    assert ollama_row_start != -1 and proxy_row_start != -1
    ollama_section = html[ollama_row_start:proxy_row_start]
    proxy_section = html[proxy_row_start : proxy_row_start + 2200]
    assert "dashboard-header-row-label" in ollama_section
    assert "dashboard-header-row-body" in ollama_section
    assert "dashboard-header-row-label" in proxy_section
    assert "dashboard-header-row-body" in proxy_section
    assert "dashboard-meta-host" in ollama_section
    assert ollama_section.index("dashboard-meta-host") < ollama_section.index("ollamaBackendStatusBadge")
    assert 'id="apiProxyEndpoint"' in proxy_section
    assert 'id="apiProxyStatusBadge"' in proxy_section
    assert 'dashboard-header-proxy-connect' in proxy_section
    assert proxy_section.index("apiProxyEndpoint") < proxy_section.index("dashboard-header-row-caption")
    assert proxy_section.index("dashboard-header-row-caption") < proxy_section.index("apiProxyStatusBadge")
    assert proxy_section.index("apiProxyStatusBadge") < proxy_section.index("dashboard-header-proxy-connect")
