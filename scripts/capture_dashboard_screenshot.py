"""Capture README dashboard and overlay modal screenshots."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "images"
BASE_URL = "http://127.0.0.1:5000"


def ensure_running_model(model: str = "lfm2.5:latest") -> None:
    ps = requests.get("http://127.0.0.1:11434/api/ps", timeout=15).json().get("models", [])
    names = {m.get("name") for m in ps}
    if model in names:
        return
    resp = requests.post(f"{BASE_URL}/api/models/start/{model}", timeout=300)
    resp.raise_for_status()
    for _ in range(90):
        ps = requests.get("http://127.0.0.1:11434/api/ps", timeout=15).json().get("models", [])
        if ps:
            return
        time.sleep(2)
    raise RuntimeError(f"Model {model} did not appear in /api/ps")


def close_modal(page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)


def wait_modal(page, selector: str, timeout: int = 60_000) -> None:
    page.wait_for_selector(f"{selector}.show", timeout=timeout)
    page.wait_for_timeout(500)


def screenshot_modal(page, selector: str, path: Path) -> None:
    wait_modal(page, selector)
    screenshot_viewport(page, path)


def reload_dashboard(page) -> None:
    page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=120_000)
    page.wait_for_selector("#runningModelsContainer .model-card--running", timeout=120_000)
    page.wait_for_timeout(800)


def running_card(page):
    return page.locator("#runningModelsContainer .model-card--running").first


def dock_ask_modal(page, side: str = "right", split_pct: float = 50) -> None:
    """Snap the open Ask? modal to a screen edge (left or right half-panel)."""
    page.evaluate(
        """({ side, splitPct }) => {
          document.documentElement.style.setProperty('--ask-dock-ask-width-vw', String(splitPct));
          try { sessionStorage.setItem('askModalDockSplitPct', String(splitPct)); } catch (_) {}
          const modal = document.getElementById('askModelModal');
          if (!modal) return;
          modal.classList.remove('ask-mode-center', 'ask-mode-float', 'ask-mode-left', 'ask-mode-right');
          modal.classList.add('ask-mode-' + side);
          document.body.classList.remove('ask-dock-left-open', 'ask-dock-right-open', 'ask-dock-floating');
          document.body.classList.add('ask-dock-' + side + '-open');
          const backdrop = document.querySelector('.modal-backdrop');
          if (backdrop) backdrop.classList.add('ask-backdrop-hidden');
          try { sessionStorage.setItem('askModalDockMode', side); } catch (_) {}
        }""",
        {"side": side, "splitPct": split_pct},
    )
    page.wait_for_timeout(600)


def screenshot_viewport(page, path: Path) -> None:
    page.screenshot(path=str(path))
    print(f"Saved {path}")


def capture_overlays(page) -> None:
    card = running_card(page)
    card.wait_for(timeout=120_000)

    card.locator('button.btn-success:has-text("Ask?")').click()
    wait_modal(page, "#askModelModal")
    screenshot_viewport(page, OUT_DIR / "overlay-ask.png")

    dock_ask_modal(page, "right")
    screenshot_viewport(page, OUT_DIR / "overlay-ask-side.png")
    close_modal(page)
    reload_dashboard(page)

    card = running_card(page)
    card.locator("button.model-action-settings-btn").click()
    wait_modal(page, "#modelSettingsModal")
    screenshot_modal(page, "#modelSettingsModal", OUT_DIR / "overlay-settings.png")
    reload_dashboard(page)

    card = running_card(page)
    card.locator('button.btn-info[onclick*="showModelInfo"]').click()
    wait_modal(page, "#modelInfoModal")
    page.wait_for_timeout(800)
    screenshot_modal(page, "#modelInfoModal", OUT_DIR / "overlay-info.png")
    reload_dashboard(page)

    page.locator(".dashboard-header-proxy-connect").click()
    wait_modal(page, "#apiProxyWizardModal")
    page.wait_for_selector("#apiProxyUrlCopy", timeout=60_000)
    page.wait_for_timeout(500)
    screenshot_modal(page, "#apiProxyWizardModal", OUT_DIR / "overlay-connect.png")


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_running_model()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
        page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=120_000)
        page.wait_for_selector("#runningModelsContainer .model-card--running", timeout=120_000)
        time.sleep(1.5)

        hero = OUT_DIR / "dashboard-hero.png"
        plain = OUT_DIR / "dashboard.png"
        page.screenshot(path=str(hero), full_page=True)
        page.screenshot(path=str(plain), full_page=True)
        print(f"Saved {hero}")
        print(f"Saved {plain}")

        capture_overlays(page)
        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
