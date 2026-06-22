"""Shared pytest fixtures for the Ollama Dashboard test suite."""
from unittest.mock import patch

import pytest


def _reset_route_rate_limiters() -> None:
    """Clear token buckets on the route module's OllamaService (module-scoped clients reuse one app)."""
    try:
        from app.routes import main as main_routes

        svc = main_routes.ollama_service
        if svc is None:
            return
        limiters = getattr(svc, 'rate_limiters', None)
        if not limiters:
            return
        for limiter in limiters.values():
            if hasattr(limiter, 'reset'):
                limiter.reset()
    except Exception:
        pass


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
        _reset_route_rate_limiters()
        yield
        _reset_route_rate_limiters()
        try:
            from app.services import upstream_http

            upstream_http.reset_pool()
        except Exception:
            pass
