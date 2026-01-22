"""Error handling utilities for Ollama API interactions.

Provides standardized error detection and classification to enable robust retry logic
and graceful degradation across the application.
"""


class TransientErrorDetector:
    """Detect and classify transient vs permanent errors."""

    # Indicators of transient errors (connection, timeout, temporary unavailability)
    TRANSIENT_INDICATORS = [
        'forcibly closed',
        'connection reset',
        'connection aborted',
        'broken pipe',
        'wsarecv',
        'timeout',
        'timed out',
        'econnreset',
        'econnrefused',
        'econnaborted',
        'enetdown',
        'enetunreach',
        'unavailable',
        'temporarily unavailable',
    ]

    # Indicators of permanent errors (not found, invalid, etc.)
    PERMANENT_INDICATORS = [
        'not found',
        'invalid',
        'unauthorized',
        'forbidden',
        'no such',
        'does not exist',
        'incompatible',
    ]

    @staticmethod
    def is_transient(error_text: str) -> bool:
        """Determine if error is transient and warrants retry.

        Args:
            error_text: Error message or response text

        Returns:
            True if error is transient (connection, timeout); False if permanent
        """
        if not error_text:
            return False

        error_lower = error_text.lower()

        # Check for explicit permanent indicators first
        for indicator in TransientErrorDetector.PERMANENT_INDICATORS:
            if indicator in error_lower:
                return False

        # Then check for transient indicators
        for indicator in TransientErrorDetector.TRANSIENT_INDICATORS:
            if indicator in error_lower:
                return True

        # Default to non-transient for unknown errors
        return False

    @staticmethod
    def classify_error(error_text: str) -> str:
        """Classify error into category.

        Returns: 'transient', 'permanent', or 'unknown'
        """
        if not error_text:
            return 'unknown'

        error_lower = error_text.lower()

        # Check permanent first
        for indicator in TransientErrorDetector.PERMANENT_INDICATORS:
            if indicator in error_lower:
                return 'permanent'

        # Then transient
        for indicator in TransientErrorDetector.TRANSIENT_INDICATORS:
            if indicator in error_lower:
                return 'transient'

        return 'unknown'


# Request timeout constants (in seconds)
TIMEOUT_GENERATE = 60  # Small generate request (warm start)
TIMEOUT_GENERATE_RETRY = 90  # Increased timeout on retry attempts
TIMEOUT_PULL = 600  # Model download (can be slow)
TIMEOUT_DELETE = 60  # Delete model
TIMEOUT_STOP = 30  # Stop model (quick operation)
TIMEOUT_PS = 10  # List running models (background update)
TIMEOUT_SHOW = 10  # Show model details
TIMEOUT_DEFAULT = 30  # Default timeout for other operations
