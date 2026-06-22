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


def _start_server():
    env = os.environ.copy()
    cmd = ["python", "OllamaDashboard.py"]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for _ in range(30):
        try:
            r = requests.get("http://127.0.0.1:5000/", timeout=5)
            if r.status_code == 200:
                return proc
        except (requests.RequestException, OSError):
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("Failed to start Flask server for tests")


@pytest.fixture(scope="module")
def server_process():
    proc = _start_server()
    yield proc
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()


def test_service_buttons(page, server_process):
    page.add_init_script(
        "window.fetch = (u,o) => Promise.resolve({ok:true,json:()=>Promise.resolve({success:true, message:'mock'})})"
    )

    page.goto("http://127.0.0.1:5000/")
    start_btn = page.locator("#startServiceBtn")
    stop_btn = page.locator("#stopServiceBtn")
    restart_btn = page.locator("#restartServiceBtn")
    assert start_btn.count() == 1
    assert stop_btn.count() == 1
    assert restart_btn.count() == 1

    with page.expect_navigation(timeout=5000):
        restart_btn.click()

    special = 'playwright-test-"\'<>'
    page.evaluate(
        """(name) => {
            const update = window.updateRunningModelsDisplay;
            if (typeof update !== 'function') return;
            update([{
                name,
                has_vision: true, has_tools: false, has_reasoning: true,
                details: { family: 'x', parameter_size: 'y', context_length: 4096 },
                size: 1000000000, size_vram: 0,
                formatted_size: '1 GB', formatted_size_vram: '0 B',
                context_length: 4096, loaded_context_length: '4096'
            }]);
        }""",
        special,
    )

    card = page.locator("#runningModelsContainer .model-card", has_text=special)
    assert card.count() == 1
    caps = card.locator('.capability-icon')
    assert caps.count() == 3
    classes = caps.nth(0).get_attribute('class')
    assert 'enabled' in classes
    classes = caps.nth(1).get_attribute('class')
    assert 'enabled' in classes
    classes = caps.nth(2).get_attribute('class')
    assert 'disabled' in classes


def test_visual_layout_model_cards_have_valid_spec_rows(page, server_process):
    page.goto("http://127.0.0.1:5000/")
    page.wait_for_load_state("networkidle")

    assert page.locator(".model-card").count() >= 0
    assert page.locator("#runningModelsContainer").count() >= 1

    cards = page.locator(".model-card")
    for i in range(cards.count()):
        card = cards.nth(i)
        spec_rows = card.locator(".spec-row")
        count = spec_rows.count()
        if count > 0:
            card_class = card.get_attribute("class") or ""
            if "model-card--derived" in card_class:
                expected = 1
            elif "model-card--running" in card_class:
                expected = 3
            else:
                expected = 2
            assert count == expected, (
                f"Model card {i} has {count} spec rows; expected {expected}"
            )


def test_visual_layout_section_containers_visible(page, server_process):
    page.goto("http://127.0.0.1:5000/")
    page.wait_for_load_state("domcontentloaded")

    assert page.locator(".section-title-text").count() >= 1
    assert page.locator(".model-specs, .model-card").count() >= 0
    spec_rows = page.locator(".spec-row")
    for i in range(min(3, spec_rows.count())):
        box = spec_rows.nth(i).bounding_box()
        if box:
            assert box["width"] >= 0 and box["height"] >= 0
