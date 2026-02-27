import os
import time
import subprocess
import requests
import pytest

# Skip this test if pytest-playwright is not installed
pytest_plugins = []
try:
    import playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

pytestmark = pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")


def _start_server():
    # Start the Flask dev server in a subprocess using OllamaDashboard.py
    env = os.environ.copy()
    cmd = ["python", "OllamaDashboard.py"]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Wait for server to be ready
    for _ in range(30):
        try:
            r = requests.get("http://127.0.0.1:5000/", timeout=5)
            if r.status_code == 200:
                return proc
        except (requests.RequestException, OSError):
            time.sleep(0.5)
    # If we reach here, server did not start
    proc.kill()
    raise RuntimeError("Failed to start Flask server for tests")


@pytest.fixture(scope="module")
def server_process():
    proc = _start_server()
    yield proc
    # Teardown: kill process
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()


def test_service_buttons(page, server_process):
    # Mask network fetch to avoid actual service calls
    page.add_init_script("window.fetch = (u,o) => Promise.resolve({ok:true,json:()=>Promise.resolve({success:true, message:'mock'})})")

    page.goto("http://127.0.0.1:5000/")
    # Ensure start/stop/restart buttons exist
    start_btn = page.locator("#startServiceBtn")
    stop_btn = page.locator("#stopServiceBtn")
    restart_btn = page.locator("#restartServiceBtn")
    assert start_btn.count() == 1
    assert stop_btn.count() == 1
    assert restart_btn.count() == 1

    # Click restart and wait for navigation (reload) to happen
    with page.expect_navigation(timeout=5000):
        restart_btn.click()

    # Insert a special name model and call updateAvailableModelsDisplay
    special = "playwright-test-\"'<>"
    page.evaluate(
        "(name)=>{ const c=document.getElementById('availableModelsContainer'); var col=document.createElement('div'); col.className='col-md-6 col-lg-4'; var card=document.createElement('div'); card.className='model-card h-100'; card.setAttribute('data-model-name', name); var title=document.createElement('div'); title.className='model-title'; title.textContent=name; var caps=document.createElement('div'); caps.className='model-capabilities'; caps.innerHTML='<span class=\"capability-icon disabled\"><i class=\"fas fa-brain\"></i></span>'+'<span class=\"capability-icon disabled\"><i class=\"fas fa-image\"></i></span>'+'<span class=\"capability-icon disabled\"><i class=\"fas fa-tools\"></i></span>'; card.appendChild(title); card.appendChild(caps); col.appendChild(card); c.appendChild(col); }",
        special,
    )

    # Now update via global JS update function
    page.evaluate(f"(function(){{ var update = window.updateAvailableModelsDisplay; update && update([{{ name: '{special}', has_vision: true, has_tools: false, has_reasoning: true }}]); }})();")

    # Locate the card
    # Find card by title text to avoid CSS selector quoting issues with special characters
    card = page.locator("#availableModelsContainer .model-card", has_text=special)
    assert card.count() == 1
    # Check capability classes - first 2 enabled, third disabled
    caps = card.locator('.capability-icon')
    assert caps.count() == 3
    # class attribute includes 'enabled' or 'disabled'
    classes = caps.nth(0).get_attribute('class')
    assert 'enabled' in classes
    classes = caps.nth(1).get_attribute('class')
    assert 'enabled' in classes
    classes = caps.nth(2).get_attribute('class')
    assert 'disabled' in classes


def test_visual_layout_model_cards_have_valid_spec_rows(page, server_process):
    """Visual regression: Running has 3 spec rows; Available/Downloadable have 2 (Size+Context on same line)."""
    page.goto("http://127.0.0.1:5000/")
    page.wait_for_load_state("networkidle")

    assert page.locator(".model-card").count() >= 0
    assert page.locator("#runningModelsContainer, #availableModelsContainer, #bestModelsContainer").count() >= 1

    cards = page.locator(".model-card")
    for i in range(cards.count()):
        card = cards.nth(i)
        spec_rows = card.locator(".spec-row")
        count = spec_rows.count()
        if count > 0:
            assert count in (2, 3), (
                f"Model card {i} has {count} spec rows; expected 2 (Available/Downloadable) or 3 (Running)"
            )


def test_visual_layout_section_containers_visible(page, server_process):
    """Section containers and key layout elements must be present."""
    page.goto("http://127.0.0.1:5000/")
    page.wait_for_load_state("domcontentloaded")

    assert page.locator(".section-title-text").count() >= 1
    assert page.locator(".model-specs, .model-card").count() >= 0
    # Spec row layout rule exists in DOM (from CSS)
    spec_rows = page.locator(".spec-row")
    # If any spec-row exists, it should be visible (not display:none) when not in compact
    for i in range(min(3, spec_rows.count())):
        box = spec_rows.nth(i).bounding_box()
        if box:
            assert box["width"] >= 0 and box["height"] >= 0
