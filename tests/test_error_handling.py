"""Unit tests for error handling utilities."""
import pytest
from app.services.error_handling import TransientErrorDetector, TIMEOUT_GENERATE, TIMEOUT_PULL


class TestTransientErrorDetector:
    """Test transient vs permanent error classification."""

    def test_is_transient_connection_reset(self):
        """Connection reset should be transient."""
        assert TransientErrorDetector.is_transient("connection reset by peer")
        assert TransientErrorDetector.is_transient("Connection Reset")

    def test_is_transient_timeout(self):
        """Timeout errors should be transient."""
        assert TransientErrorDetector.is_transient("request timeout")
        assert TransientErrorDetector.is_transient("connection timed out")
        assert TransientErrorDetector.is_transient("Timeout waiting for response")

    def test_is_transient_broken_pipe(self):
        """Broken pipe should be transient."""
        assert TransientErrorDetector.is_transient("broken pipe")
        assert TransientErrorDetector.is_transient("Broken Pipe Error")

    def test_is_transient_forcibly_closed(self):
        """Forcibly closed should be transient."""
        assert TransientErrorDetector.is_transient("forcibly closed")
        assert TransientErrorDetector.is_transient("connection forcibly closed")

    def test_is_transient_wsarecv(self):
        """WSARECV errors (Windows) should be transient."""
        assert TransientErrorDetector.is_transient("wsarecv failed")
        assert TransientErrorDetector.is_transient("WSARECV")

    def test_is_transient_econnrefused(self):
        """Connection refused should be transient."""
        assert TransientErrorDetector.is_transient("econnrefused")
        assert TransientErrorDetector.is_transient("connection refused")

    def test_is_permanent_not_found(self):
        """Not found should be permanent."""
        assert not TransientErrorDetector.is_transient("model not found")
        assert not TransientErrorDetector.is_transient("Not Found")

    def test_is_permanent_invalid(self):
        """Invalid errors should be permanent."""
        assert not TransientErrorDetector.is_transient("invalid model name")
        assert not TransientErrorDetector.is_transient("Invalid Request")

    def test_is_permanent_unauthorized(self):
        """Unauthorized should be permanent."""
        assert not TransientErrorDetector.is_transient("unauthorized")
        assert not TransientErrorDetector.is_transient("Unauthorized access")

    def test_is_permanent_forbidden(self):
        """Forbidden should be permanent."""
        assert not TransientErrorDetector.is_transient("forbidden")
        assert not TransientErrorDetector.is_transient("Forbidden")

    def test_is_permanent_no_such(self):
        """'No such' errors should be permanent."""
        assert not TransientErrorDetector.is_transient("no such model")
        assert not TransientErrorDetector.is_transient("No such file")

    def test_is_unknown_error(self):
        """Unknown errors default to non-transient."""
        assert not TransientErrorDetector.is_transient("some random error")
        assert not TransientErrorDetector.is_transient("unexpected failure")

    def test_is_empty_error(self):
        """Empty error text defaults to non-transient."""
        assert not TransientErrorDetector.is_transient("")
        assert not TransientErrorDetector.is_transient(None)

    def test_classify_error_transient(self):
        """Classify transient errors correctly."""
        assert TransientErrorDetector.classify_error("connection reset") == 'transient'
        assert TransientErrorDetector.classify_error("timeout") == 'transient'

    def test_classify_error_permanent(self):
        """Classify permanent errors correctly."""
        assert TransientErrorDetector.classify_error("not found") == 'permanent'
        assert TransientErrorDetector.classify_error("invalid") == 'permanent'

    def test_classify_error_unknown(self):
        """Classify unknown errors correctly."""
        assert TransientErrorDetector.classify_error("something failed") == 'unknown'
        assert TransientErrorDetector.classify_error("") == 'unknown'

    def test_case_insensitive(self):
        """Error detection should be case-insensitive."""
        assert TransientErrorDetector.is_transient("CONNECTION RESET")
        assert TransientErrorDetector.is_transient("TiMeOuT")
        assert not TransientErrorDetector.is_transient("NOT FOUND")


class TestTimeoutConstants:
    """Test timeout constant values."""

    def test_timeout_constants_exist(self):
        """All timeout constants should be defined."""
        assert TIMEOUT_GENERATE == 60
        assert TIMEOUT_PULL == 600

    def test_timeout_values_reasonable(self):
        """Timeout values should be reasonable."""
        assert TIMEOUT_GENERATE > 0
        assert TIMEOUT_PULL > TIMEOUT_GENERATE
        assert TIMEOUT_PULL == 600  # 10 minutes for downloads
