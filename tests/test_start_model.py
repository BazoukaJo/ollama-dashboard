import unittest
from unittest.mock import patch, MagicMock
from app import create_app

class TestStartModelRoute(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_start_model_success(self, mock_status, mock_running, mock_requests_post):
        mock_status.return_value = True
        mock_running.return_value = []  # Model not already running

        # Simulate successful generate response
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.text = 'ok'
        mock_requests_post.return_value = success_resp

        resp = self.client.post('/api/models/start/test-model')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('started successfully', data['message'])

    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_start_model_not_running_service(self, mock_status, mock_running, mock_requests_post):
        mock_status.return_value = False  # Service down
        mock_running.return_value = []

        resp = self.client.post('/api/models/start/test-model')
        self.assertEqual(resp.status_code, 503)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('service is not running', data['message'])

    @patch('app.routes.main.requests.post')
    @patch('app.routes.main.ollama_service.get_running_models')
    @patch('app.routes.main.ollama_service.get_service_status')
    def test_start_model_already_running(self, mock_status, mock_running, mock_requests_post):
        mock_status.return_value = True
        mock_running.return_value = [{'name': 'test-model'}]

        resp = self.client.post('/api/models/start/test-model')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('already running', data['message'])

if __name__ == '__main__':
    unittest.main()
