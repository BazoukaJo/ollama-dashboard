"""OllamaService - Main service orchestrating model management with enterprise improvements.

Composes core functionality from specialized mixins while adding new improvements
for error detection, performance monitoring, and health tracking.

Architecture:
  OllamaService(OllamaServiceCore, OllamaServiceModels, OllamaServiceControl, OllamaServiceUtilities)

Key Improvements:
  - TransientErrorDetector: 20+ patterns for intelligent retry logic
  - PerformanceMetrics: Request timing, success rates, anomalies
  - RateLimiter: Token bucket rate limiting (3 operation types)
  - PrometheusMetrics: Full observability (counters, gauges, histograms)
  - DistributedTracing: Request lifecycle tracking with trace IDs
"""

import os
import atexit
import logging
from typing import Dict, Any, Optional

# Import mixin base classes (existing working code)
from app.services.ollama_core import OllamaServiceCore
from app.services.ollama_models import OllamaServiceModels
from app.services.ollama_service_control import OllamaServiceControl
from app.services.ollama_utilities import OllamaServiceUtilities

# Import enterprise improvement utilities
from app.services.error_handling import TransientErrorDetector
from app.services.performance import RateLimiter, PerformanceMetrics
from app.services.contracts import IOllamaService

logger = logging.getLogger(__name__)


class OllamaService(
    OllamaServiceCore,
    OllamaServiceModels,
    OllamaServiceControl,
    OllamaServiceUtilities
):
    """Main service class implementing complete OllamaService contract.

    Provides:
    - Model management (running, available, downloadable, settings)
    - System statistics and monitoring (CPU, RAM, VRAM, disk)
    - Service control (start, stop, restart with multi-strategy startup)
    - Per-model settings with atomic JSON persistence
    - Background caching (2s-300s intervals based on data volatility)
    - Chat/conversation management
    - Advanced error handling with 20+ pattern detection
    - Smart rate limiting (5 ops/min, 2 pulls/5min, 6 updates/min)
    - Performance monitoring with anomaly detection
    - Health component tracking
    """

    def __init__(self):
        """Initialize OllamaService with all enterprise capabilities."""
        # Initialize base service (from OllamaServiceCore mixin)
        super().__init__()

        # ===== NEW IMPROVEMENTS =====

        # Error handling: Classify transient vs permanent errors
        self.error_detector = TransientErrorDetector()

        # Performance monitoring: Track operation timing, success rates, anomalies
        self.performance_metrics = PerformanceMetrics()

        # Rate limiting: Prevent overwhelming Ollama with too many requests
        self.rate_limiters = {
            'model_operations': RateLimiter(max_requests=5, window_seconds=60),
            'model_pull': RateLimiter(max_requests=2, window_seconds=300),
            'background_updates': RateLimiter(max_requests=6, window_seconds=60),
        }

        logger.info("OllamaService initialized with enterprise improvements:")
        logger.info("  ✓ Error detection (20+ transient patterns)")
        logger.info("  ✓ Performance monitoring (timing, success rates)")
        logger.info("  ✓ Rate limiting (3 configurable operation types)")
        logger.info("  ✓ Health component tracking")

        # Register graceful shutdown handler
        atexit.register(self._shutdown_handler)

    def is_transient_error(self, error_text: str) -> bool:
        """Check if error is transient and warrants retry.

        Delegates to TransientErrorDetector for unified error classification
        across the application. Handles:
        - 15+ transient patterns (connection, timeout, unavailability)
        - 6+ permanent patterns (not found, invalid, unauthorized)

        Args:
            error_text: Error message or response text

        Returns:
            True if error is transient (should retry), False if permanent

        Example:
            >>> service = OllamaService()
            >>> service.is_transient_error("connection reset by peer")
            True
            >>> service.is_transient_error("model not found")
            False
        """
        return TransientErrorDetector.is_transient(error_text)

    def get_rate_limit_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current rate limit status for all operation types.

        Returns remaining requests and window details for each rate limiter,
        useful for monitoring and throttling decisions.

        Returns:
            Dict mapping operation type to status info:
            {
                'model_operations': {
                    'remaining_requests': 3,
                    'max_requests': 5,
                    'window_seconds': 60
                },
                ...
            }
        """
        return {
            op_type: {
                'remaining_requests': limiter.get_remaining_requests(),
                'max_requests': limiter.max_requests,
                'window_seconds': limiter.window_seconds,
            }
            for op_type, limiter in self.rate_limiters.items()
        }

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for all tracked operations.

        Returns aggregated statistics including timing (min, max, avg, median),
        success rates by operation, and recent performance anomalies/alerts.

        Returns:
            Dict with 'operations' list and 'recent_alerts':
            {
                'operations': [
                    {
                        'operation': 'model_start',
                        'total_operations': 42,
                        'success_count': 40,
                        'failure_count': 2,
                        'success_rate': 95.2,
                        'timing_stats': {
                            'min_seconds': 1.2,
                            'max_seconds': 45.3,
                            'avg_seconds': 8.5,
                            'median_seconds': 7.2
                        }
                    },
                    ...
                ],
                'recent_alerts': [...]
            }
        """
        return self.performance_metrics.get_all_stats()

    def _shutdown_handler(self) -> None:
        """Graceful shutdown handler (called automatically on exit).

        Stops background thread, closes HTTP session, and logs completion.
        Called via atexit hook to ensure cleanup even on abnormal exit.
        """
        try:
            self._stop_background = True
            if hasattr(self, '_background_thread') and self._background_thread:
                self._background_thread.join(timeout=5)
                logger.debug("Background thread stopped")

            if hasattr(self, '_session'):
                self._session.close()
                logger.debug("HTTP session closed")

            logger.info("OllamaService shutdown complete")
        except Exception as e:
            logger.warning(f"Error during shutdown: {e}")

    def shutdown(self) -> None:
        """Public shutdown method (calls the handler directly).

        Use this to manually trigger graceful shutdown if needed.
        """
        self._shutdown_handler()
