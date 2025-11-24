"""
Comprehensive tests for model capability detection and display system.
Tests vision, tools, and reasoning capability detection across all model sources.
"""
import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.services.ollama import OllamaService


@pytest.fixture(scope="module")
def app():
    """Create test app instance."""
    return create_app()


@pytest.fixture(scope="module")
def client(app):
    """Create test client."""
    with app.test_client() as c:
        yield c


@pytest.fixture
def ollama_service(app):
    """Create OllamaService instance with app context."""
    service = OllamaService()
    service.init_app(app)
    return service


class TestCapabilityDetection:
    """Test capability detection logic in OllamaService."""

    def test_detect_vision_by_name_llava(self, ollama_service):
        """Test vision detection for llava model."""
        model = {'name': 'llava:latest', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_vision'] is True
        assert capabilities['has_tools'] is False
        assert capabilities['has_reasoning'] is False

    def test_detect_vision_by_name_qwen3_vl(self, ollama_service):
        """Test vision detection for qwen3-vl model."""
        model = {'name': 'qwen3-vl:8b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_vision'] is True

    def test_detect_vision_by_families_clip(self, ollama_service):
        """Test vision detection by families containing 'clip'."""
        model = {
            'name': 'custom-model',
            'details': {'families': ['base', 'clip', 'text']}
        }
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_vision'] is True

    def test_detect_vision_by_families_projector(self, ollama_service):
        """Test vision detection by families containing 'projector'."""
        model = {
            'name': 'custom-model',
            'details': {'families': ['base', 'projector']}
        }
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_vision'] is True

    def test_detect_tools_llama3_1(self, ollama_service):
        """Test tools detection for llama3.1 model."""
        model = {'name': 'llama3.1:8b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_tools'] is True
        assert capabilities['has_vision'] is False

    def test_detect_tools_qwen2_5(self, ollama_service):
        """Test tools detection for qwen2.5 model."""
        model = {'name': 'qwen2.5:7b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_tools'] is True

    def test_detect_tools_mistral(self, ollama_service):
        """Test tools detection for mistral model."""
        model = {'name': 'mistral:latest', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_tools'] is True

    def test_no_tools_for_old_versions(self, ollama_service):
        """Test that old llama3.0 doesn't get tool capability."""
        model = {'name': 'llama3.0:8b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_tools'] is False

    def test_detect_reasoning_deepseek_r1(self, ollama_service):
        """Test reasoning detection for deepseek-r1 model."""
        model = {'name': 'deepseek-r1:8b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_reasoning'] is True
        assert capabilities['has_vision'] is False
        assert capabilities['has_tools'] is False

    def test_detect_reasoning_qwq(self, ollama_service):
        """Test reasoning detection for qwq model."""
        model = {'name': 'qwq:32b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_reasoning'] is True

    def test_detect_reasoning_marco_o1(self, ollama_service):
        """Test reasoning detection for marco-o1 model."""
        model = {'name': 'marco-o1:7b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_reasoning'] is True

    def test_no_capabilities_basic_model(self, ollama_service):
        """Test that basic text model has no special capabilities."""
        model = {'name': 'llama2:7b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)
        assert capabilities['has_vision'] is False
        assert capabilities['has_tools'] is False
        assert capabilities['has_reasoning'] is False


class TestRunningModelsCapabilities:
    """Test that running models API includes capability flags."""

    @patch('requests.Session.get')
    def test_running_models_include_capabilities(self, mock_get, ollama_service):
        """Test that get_running_models returns models with capability flags."""
        # Mock Ollama API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'models': [{
                'name': 'llava:latest',
                'size': 4500000000,
                'digest': 'abc123',
                'details': {
                    'families': ['llava', 'clip'],
                    'parameter_size': '7B',
                    'quantization_level': 'Q4_K_M'
                },
                'expires_at': None
            }]
        }
        mock_get.return_value = mock_response

        models = ollama_service.get_running_models()

        assert len(models) == 1
        model = models[0]

        # Verify structure includes all required fields
        assert 'name' in model
        assert 'has_vision' in model
        assert 'has_tools' in model
        assert 'has_reasoning' in model

        # Verify correct capability detection for llava
        assert model['has_vision'] is True
        assert model['has_tools'] is False
        assert model['has_reasoning'] is False

    @patch('requests.Session.get')
    def test_running_models_tools_capability(self, mock_get, ollama_service):
        """Test that llama3.1 model shows tools capability."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'models': [{
                'name': 'llama3.1:8b',
                'size': 4500000000,
                'digest': 'abc123',
                'details': {
                    'families': ['llama'],
                    'parameter_size': '8B',
                    'quantization_level': 'Q4_K_M'
                },
                'expires_at': None
            }]
        }
        mock_get.return_value = mock_response

        models = ollama_service.get_running_models()
        model = models[0]

        assert model['has_tools'] is True
        assert model['has_vision'] is False
        assert model['has_reasoning'] is False

    @patch('requests.Session.get')
    def test_running_models_reasoning_capability(self, mock_get, ollama_service):
        """Test that deepseek-r1 model shows reasoning capability."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'models': [{
                'name': 'deepseek-r1:8b',
                'size': 4500000000,
                'digest': 'abc123',
                'details': {
                    'families': ['deepseek'],
                    'parameter_size': '8B',
                    'quantization_level': 'Q4_K_M'
                },
                'expires_at': None
            }]
        }
        mock_get.return_value = mock_response

        models = ollama_service.get_running_models()
        model = models[0]

        assert model['has_reasoning'] is True
        assert model['has_vision'] is False
        assert model['has_tools'] is False


class TestAvailableModelsCapabilities:
    """Test that available models API includes capability flags."""

    @patch('requests.Session.get')
    def test_available_models_include_capabilities(self, mock_get, ollama_service):
        """Test that get_available_models returns models with capability flags."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'models': [
                {
                    'name': 'llava:latest',
                    'size': 4500000000,
                    'digest': 'abc123',
                    'details': {'families': ['llava', 'clip']}
                },
                {
                    'name': 'llama3.1:8b',
                    'size': 4500000000,
                    'digest': 'def456',
                    'details': {'families': ['llama']}
                }
            ]
        }
        mock_get.return_value = mock_response

        models = ollama_service.get_available_models()

        assert len(models) == 2

        # Check llava has vision
        llava = models[0]
        assert llava['has_vision'] is True
        assert llava['has_tools'] is False
        assert llava['has_reasoning'] is False

        # Check llama3.1 has tools
        llama = models[1]
        assert llama['has_tools'] is True
        assert llama['has_vision'] is False
        assert llama['has_reasoning'] is False


class TestAPIEndpoints:
    """Test API endpoints return models with capabilities."""

    @patch('app.routes.main.ollama_service.get_running_models')
    def test_api_running_models_returns_capabilities(self, mock_get_running, client):
        """Test /api/models/running endpoint returns capability flags."""
        mock_get_running.return_value = [
            {
                'name': 'llava:latest',
                'families_str': 'llava, clip',
                'parameter_size': '7B',
                'size': '4.5 GB',
                'expires_at': None,
                'details': {},
                'has_vision': True,
                'has_tools': False,
                'has_reasoning': False
            }
        ]

        response = client.get('/api/models/running')
        assert response.status_code == 200

        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == 1

        model = data[0]
        assert 'has_vision' in model
        assert 'has_tools' in model
        assert 'has_reasoning' in model
        assert model['has_vision'] is True

    @patch('app.routes.main.ollama_service.get_available_models')
    def test_api_available_models_returns_capabilities(self, mock_get_available, client):
        """Test /api/models/available endpoint returns capability flags."""
        mock_get_available.return_value = [
            {
                'name': 'qwen2.5:7b',
                'has_vision': False,
                'has_tools': True,
                'has_reasoning': False
            }
        ]

        response = client.get('/api/models/available')
        assert response.status_code == 200

        data = response.get_json()
        models = data.get('models', [])
        assert len(models) == 1

        model = models[0]
        assert model['has_tools'] is True
        assert model['has_vision'] is False


class TestDownloadableModelsCapabilities:
    """Test downloadable models have explicit capability flags."""

    def test_downloadable_best_models_have_capabilities(self, client):
        """Test that downloadable best models include capability flags."""
        response = client.get('/api/models/downloadable?category=best')
        assert response.status_code == 200

        data = response.get_json()
        models = data.get('models', [])

        # Find vision model
        llava = next((m for m in models if m['name'] == 'llava'), None)
        assert llava is not None
        assert llava['has_vision'] is True

        # Find tools model
        llama31 = next((m for m in models if 'llama3.1' in m['name']), None)
        if llama31:
            assert llama31['has_tools'] is True

    def test_downloadable_all_models_have_capabilities(self, client):
        """Test that all downloadable models include capability flags."""
        response = client.get('/api/models/downloadable?category=all')
        assert response.status_code == 200

        data = response.get_json()
        models = data.get('models', [])

        # Verify all models have capability fields
        for model in models:
            assert 'has_vision' in model
            assert 'has_tools' in model
            assert 'has_reasoning' in model
            assert isinstance(model['has_vision'], bool)
            assert isinstance(model['has_tools'], bool)
            assert isinstance(model['has_reasoning'], bool)


class TestMultipleCapabilities:
    """Test models with multiple capabilities."""

    def test_qwen3_vl_has_vision_and_tools(self, ollama_service):
        """Test that qwen3-vl can have both vision and tools capabilities."""
        model = {'name': 'qwen3-vl:8b', 'details': {}}
        capabilities = ollama_service._detect_model_capabilities(model)

        # qwen3-vl has vision by name
        assert capabilities['has_vision'] is True
        # qwen3 pattern should match tools
        assert capabilities['has_tools'] is True
        assert capabilities['has_reasoning'] is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
