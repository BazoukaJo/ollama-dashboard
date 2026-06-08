"""Shared pytest fixtures for the Ollama Dashboard test suite."""
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def no_background_stats_thread(request):
    """Prevent the BackgroundDataCollector thread from starting during tests.

    This thread polls nvidia-smi via subprocess.run every ~1 second.  When a test
    patches subprocess.run, those nvidia-smi calls leak into the mock and break
    call-count assertions (e.g. assert_called_once() fails because it was actually
    called four times — three from the background thread, one from the code under
    test).

    Tests that explicitly need the real background thread can opt out by marking
    themselves with the 'live_background_thread' marker:

        @pytest.mark.live_background_thread
        def test_something_that_needs_real_background_polling():
            ...
    """
    if request.node.get_closest_marker('live_background_thread'):
        yield
        return
    with patch('app.services.ollama_core.OllamaServiceCore._start_background_updates'):
        yield
