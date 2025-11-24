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


def test_reload_and_service_buttons(page, server_process):
    # Mask network fetch to avoid actual service calls
    page.add_init_script("window.fetch = (u,o) => Promise.resolve({ok:true,json:()=>Promise.resolve({success:true, message:'mock'})})")

    page.goto("http://127.0.0.1:5000/")
    # Ensure reload button exists
    reload_btn = page.locator("#reloadAppBtn")
    assert reload_btn.count() == 1
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
