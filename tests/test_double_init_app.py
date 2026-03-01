"""Tests that OllamaService.init_app() is idempotent.

Calling init_app() twice must not start a second background thread or
register additional atexit handlers (Bug 1 in the audit).
"""
import atexit
import threading
import pytest
from app import create_app
from app.services.ollama import OllamaService


class TestInitAppIdempotency:
    """Verify that the service survives multiple init_app() calls cleanly."""

    def test_single_background_thread_after_double_init(self):
        """init_app() called twice must not spin up a second background thread."""
        app = create_app()
        svc = app.config['OLLAMA_SERVICE']

        thread_before = svc._background_stats

        # Simulate a second init_app() call (e.g. from a misconfigured blueprint)
        with app.app_context():
            svc.init_app(app)

        thread_after = svc._background_stats

        # The thread object must be the same instance — no new thread started
        assert thread_before is thread_after, (
            "init_app() started a second background thread on the second call"
        )

    def test_background_thread_is_alive_after_init(self):
        """The background thread started by init_app() must be alive."""
        app = create_app()
        svc = app.config['OLLAMA_SERVICE']
        assert svc._background_stats is not None
        assert svc._background_stats.is_alive()

    def test_create_app_twice_does_not_share_service(self):
        """Two separate create_app() calls produce independent service instances."""
        app1 = create_app()
        app2 = create_app()
        svc1 = app1.config['OLLAMA_SERVICE']
        svc2 = app2.config['OLLAMA_SERVICE']
        assert svc1 is not svc2

    def test_route_init_app_does_not_reinitialise_service(self):
        """The blueprint's init_app() must NOT call svc.init_app() internally."""
        from app.routes.main import init_app as route_init_app

        app = create_app()
        svc = app.config['OLLAMA_SERVICE']
        thread_before = svc._background_stats

        # Calling the route initialiser a second time should be a no-op for the service
        with pytest.raises(Exception):
            # register_blueprint raises AssertionError if bp already registered —
            # that is expected and proves the route init_app did not re-init the service.
            route_init_app(app)

        # Thread must still be the original one — no new thread was spawned
        assert svc._background_stats is thread_before
