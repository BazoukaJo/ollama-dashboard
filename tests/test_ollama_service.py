import unittest
from unittest.mock import patch
from app import create_app

class TestOllamaService(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_ping_endpoint(self):
        response = self.client.get('/ping')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

    def test_api_test_endpoint(self):
        response = self.client.get('/api/test')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "API is working"})

    @patch('app.services.ollama.requests.get')
    def test_index_route_system_resources(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'models': []}

        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'System Resources', response.data)

    def test_service_status_endpoint(self):
        response = self.client.get('/api/service/status')
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn('status', data)
        self.assertIn('running', data)

    @patch('app.services.ollama.OllamaService.start_service')
    def test_start_service_endpoint(self, mock_start):
        mock_start.return_value = {"success": True, "message": "Ollama service started successfully"}

        response = self.client.post('/api/service/start')
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn('success', data)
        self.assertIn('message', data)

    @patch('app.services.ollama.OllamaService.stop_service')
    def test_stop_service_endpoint(self, mock_stop):
        mock_stop.return_value = {"success": True, "message": "Ollama service stopped successfully"}

        response = self.client.post('/api/service/stop')
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertIn('success', data)
        self.assertIn('message', data)

if __name__ == '__main__':
    unittest.main()
