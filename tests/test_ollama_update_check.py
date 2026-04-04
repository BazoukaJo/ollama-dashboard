"""Tests for startup Ollama vs GitHub release version comparison."""
# pylint: disable=protected-access
import unittest
from unittest.mock import MagicMock, patch

from app.services import ollama_update_check as ouc


class TestVersionCompare(unittest.TestCase):
    def test_compare_greater(self):
        self.assertGreater(ouc._compare_versions("v0.6.0", "0.5.4"), 0)
        self.assertGreater(ouc._compare_versions("0.10.0", "0.9.9"), 0)

    def test_compare_equal(self):
        self.assertEqual(ouc._compare_versions("v1.2.3", "1.2.3"), 0)

    def test_compare_less(self):
        self.assertLess(ouc._compare_versions("0.5.0", "0.5.4"), 0)


class TestStartupCheck(unittest.TestCase):
    @patch.object(ouc, "fetch_latest_ollama_tag", return_value="v9.99.0")
    def test_update_available_when_newer(self, _mock_fetch):
        svc = MagicMock()
        svc.get_ollama_version.return_value = "0.1.0"
        info = ouc.run_startup_ollama_update_check(svc)
        self.assertTrue(info["update_available"])
        self.assertEqual(info["latest_version"], "v9.99.0")

    @patch.object(ouc, "fetch_latest_ollama_tag", return_value="v1.0.0")
    def test_no_update_when_current_same_or_newer(self, _mock_fetch):
        svc = MagicMock()
        svc.get_ollama_version.return_value = "1.0.0"
        info = ouc.run_startup_ollama_update_check(svc)
        self.assertFalse(info["update_available"])

    def test_no_update_when_version_unknown(self):
        svc = MagicMock()
        svc.get_ollama_version.return_value = "Unknown"
        info = ouc.run_startup_ollama_update_check(svc)
        self.assertFalse(info["update_available"])
        self.assertIsNone(info["latest_version"])


if __name__ == "__main__":
    unittest.main()
