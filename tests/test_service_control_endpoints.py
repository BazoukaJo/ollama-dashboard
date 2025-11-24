import unittest
from unittest.mock import patch
from app import create_app


class TestServiceControls(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    @patch('app.routes.main.ollama_service.restart_service')
    def test_restart_service_endpoint(self, mock_restart):
        mock_restart.return_value = {"success": True, "message": "Ollama service restarted successfully"}
        response = self.client.post('/api/service/restart')
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn('success', data)
        self.assertTrue(data['success'])

    @patch('app.routes.main.ollama_service.stop_service')
    def test_stop_service_endpoint(self, mock_stop):
        mock_stop.return_value = {"success": True, "message": "Ollama service stopped successfully"}
        response = self.client.post('/api/service/stop')
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn('success', data)
        self.assertTrue(data['success'])

    @patch('app.routes.main.ollama_service.start_service')
    def test_start_service_endpoint(self, mock_start):
        mock_start.return_value = {"success": True, "message": "Ollama service started successfully"}
        response = self.client.post('/api/service/start')
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn('success', data)
        self.assertTrue(data['success'])


if __name__ == '__main__':
    unittest.main()
