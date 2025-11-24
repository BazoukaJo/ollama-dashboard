import unittest
from unittest.mock import patch
from app.services.ollama import OllamaService


class DummyCompleted:
    def __init__(self, returncode=0, stdout=''):
        self.returncode = returncode
        self.stdout = stdout


class TestOllamaServiceStartStopIntegration(unittest.TestCase):

    @patch('subprocess.run')
    @patch('platform.system')
    def test_start_service_windows_sc_success(self, mock_platform_system, mock_subproc_run):
        mock_platform_system.return_value = 'Windows'

        # Simulate `sc start Ollama` success -> returncode 0
        def run_side_effect(args, **kwargs):
            if isinstance(args, list) and args[0] == 'sc':
                return DummyCompleted(returncode=0, stdout='SERVICE_NAME: Ollama\nSTATE: START_PENDING')
            if isinstance(args, list) and args[0] == 'tasklist':
                return DummyCompleted(returncode=0, stdout='ollama.exe')
            # Default fallback
            return DummyCompleted(returncode=1, stdout='')

        mock_subproc_run.side_effect = run_side_effect

        svc = OllamaService()
        res = svc.start_service()
        self.assertTrue(res['success'])

    @patch('subprocess.run')
    @patch('platform.system')
    def test_start_service_linux_systemctl_success(self, mock_platform_system, mock_subproc_run):
        mock_platform_system.return_value = 'Linux'

        def run_side_effect(args, **kwargs):
            # systemctl start ollama
            if isinstance(args, list) and args[0] == 'systemctl':
                return DummyCompleted(returncode=0, stdout='')
            # pgrep will be used to detect running processes
            if isinstance(args, list) and args[0] == 'pgrep':
                return DummyCompleted(returncode=0, stdout='1234')
            return DummyCompleted(returncode=1, stdout='')

        mock_subproc_run.side_effect = run_side_effect

        svc = OllamaService()
        res = svc.start_service()
        self.assertTrue(res['success'])

    @patch('subprocess.run')
    @patch('platform.system')
    def test_stop_service_linux_pkill_success(self, mock_platform_system, mock_subproc_run):
        mock_platform_system.return_value = 'Linux'

        def run_side_effect(args, **kwargs):
            if args and args[0] == 'pkill':
                return DummyCompleted(returncode=0, stdout='')
            return DummyCompleted(returncode=1, stdout='')

        mock_subproc_run.side_effect = run_side_effect

        svc = OllamaService()
        res = svc.stop_service()
        self.assertTrue(res['success'])


if __name__ == '__main__':
    unittest.main()
