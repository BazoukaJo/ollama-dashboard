import threading
import time
import unittest
import requests
from contextlib import suppress
from typing import TYPE_CHECKING

from app import create_app

# Conditional imports for optional dependencies
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Type hints for static analysis (only when selenium is available)
if TYPE_CHECKING:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import WebDriverException


@unittest.skipUnless(SELENIUM_AVAILABLE, "Selenium not available; skipping UI tests")
class TestServiceControlsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        # Start Flask app in background thread
        cls.server_thread = threading.Thread(target=cls.app.run, kwargs={'host':'127.0.0.1','port':5000, 'debug': False}, daemon=True)
        cls.server_thread.start()
        # Wait longer for server to be fully ready
        for _ in range(10):
            try:
                response = requests.get('http://127.0.0.1:5000/', timeout=1)
                if response.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            raise RuntimeError("Flask server failed to start within timeout")

    @classmethod
    def tearDownClass(cls):
        # Can't gracefully stop Flask dev server easily here - rely on thread daemon exit
        pass

    def setUp(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
        except (WebDriverException, OSError) as e:
            self.skipTest(f"Chrome WebDriver not available: {e}")

    def tearDown(self):
        with suppress(Exception):
            self.driver.quit()

    def test_service_buttons_present_and_handlers(self):
        url = 'http://127.0.0.1:5000/'
        self.driver.get(url)

        # Ensure UI buttons present
        start_btn = self.driver.find_element(By.ID, 'startServiceBtn')
        stop_btn = self.driver.find_element(By.ID, 'stopServiceBtn')
        restart_btn = self.driver.find_element(By.ID, 'restartServiceBtn')
        self.assertIsNotNone(start_btn)
        self.assertIsNotNone(stop_btn)
        self.assertIsNotNone(restart_btn)

        # Override fetch to avoid network side-effects
        self.driver.execute_script("window._origFetch = window.fetch; window.fetch = (u,o) => Promise.resolve({ok:true,json:()=>Promise.resolve({success:true,message:'mocked'})});")

        # Check that JS functions exist
        t = self.driver.execute_script('return typeof restartOllamaService;')
        self.assertIn(t, ('function', 'object'))

        # Click restart and ensure no JS error was thrown by checking browser logs
        restart_btn.click()
        time.sleep(1)
        # Read browser console logs for any SEVERE errors
        logs = []
        try:
            logs = self.driver.get_log('browser')
        except (AttributeError, WebDriverException):
            # Some drivers may not support log retrieval
            logs = []

        severe_logs = [l for l in logs if l.get('level') == 'SEVERE']
        self.assertEqual(len(severe_logs), 0, f"Severe console logs found: {severe_logs}")

        # Find the first available model item and record its capabilities classes
        # Use a specific model name that exists in the demo data
        modelName = 'qwen3-vl:4b'
        # JS will try to find a card with .model-title containing the name
        script = f"""
                (function() {{
                    var update = window.updateAvailableModelsDisplay;
                    if (typeof update !== 'function') return false;
                    // Replace available models with a test entry toggling capabilities
                    var testModel = {{ name: '{modelName}', has_vision: true, has_tools: false, has_reasoning: true }};
                    update([testModel]);
                    return true;
                }})();
            """
        res = self.driver.execute_script(script)
        self.assertTrue(res, 'Failed to call updateAvailableModelsDisplay')
        time.sleep(0.5)

        # Now query the card for the model and verify capability classes
        # Find the card by title text
        cards = self.driver.find_elements(By.CSS_SELECTOR, '#availableModelsContainer .model-card')
        matched_card = None
        for c in cards:
            title = c.find_element(By.CSS_SELECTOR, '.model-title').text.strip()
            if title == modelName:
                matched_card = c
                break
        self.assertIsNotNone(matched_card, 'Target model card not found')
        caps = matched_card.find_elements(By.CSS_SELECTOR, '.capability-icon')
        self.assertEqual(len(caps), 3)
        # Reasoning (first) -> enabled
        self.assertIn('enabled', caps[0].get_attribute('class'))
        # Vision (second) -> enabled
        self.assertIn('enabled', caps[1].get_attribute('class'))
        # Tools (third) -> disabled
        self.assertIn('disabled', caps[2].get_attribute('class'))

    def test_special_char_model_names_ui(self):
        # Ensures updateAvailableModelsDisplay and related DOM lookup works
        url = 'http://127.0.0.1:5000/'
        self.driver.get(url)

        # Create a model with special characters in its name and add a card to DOM
        special_name = "weird\"name'\n<>"
        script_insert = f"""
            (function() {{
                var container = document.getElementById('availableModelsContainer');
                var col = document.createElement('div'); col.className = 'col-md-6 col-lg-4';
                var card = document.createElement('div'); card.className = 'model-card h-100';
                card.setAttribute('data-model-name', '{special_name}');
                var title = document.createElement('div'); title.className = 'model-title'; title.textContent = '{special_name}';
                var caps = document.createElement('div'); caps.className = 'model-capabilities';
                caps.innerHTML = '<span class="capability-icon disabled"><i class="fas fa-brain"></i></span>' +
                                 '<span class="capability-icon disabled"><i class="fas fa-image"></i></span>' +
                                 '<span class="capability-icon disabled"><i class="fas fa-tools"></i></span>';
                card.appendChild(title); card.appendChild(caps); col.appendChild(card); container.appendChild(col);
                return true;
            }})();
        """
        self.driver.execute_script(script_insert)

        # Mask fetch to prevent network calls
        self.driver.execute_script("window._origFetch = window.fetch; window.fetch = (u,o) => Promise.resolve({ok:true,json:()=>Promise.resolve({success:true,message:'mocked'})});")

        # Update with a matching model (enable vision + reasoning, disable tools)
        script_update = f"(function(){{ var update = window.updateAvailableModelsDisplay; update && update([{{ name: '{special_name}', has_vision: true, has_tools: false, has_reasoning: true }}]); return true; }})();"
        res = self.driver.execute_script(script_update)
        self.assertTrue(res, 'Failed to call updateAvailableModelsDisplay for special name')
        time.sleep(0.2)

        # Find the inserted card and validate capability classes
        cards = self.driver.find_elements(By.CSS_SELECTOR, '#availableModelsContainer .model-card')
        matched = None
        for c in cards:
            try:
                title = c.find_element(By.CSS_SELECTOR, '.model-title').text.strip()
            except Exception:
                title = ''
            if title == special_name:
                matched = c
                break
        self.assertIsNotNone(matched, 'Inserted special-name model card not found')
        caps = matched.find_elements(By.CSS_SELECTOR, '.capability-icon')
        self.assertEqual(len(caps), 3)
        self.assertIn('enabled', caps[0].get_attribute('class'))
        self.assertIn('enabled', caps[1].get_attribute('class'))
        self.assertIn('disabled', caps[2].get_attribute('class'))


if __name__ == '__main__':
    unittest.main()
