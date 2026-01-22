"""Prometheus metrics export for observability integration.

Provides:
- Prometheus-compatible metrics endpoint
- Gauge, counter, and histogram metrics
- Application health and performance metrics
- Rate limit and retry metrics
- Model operation metrics
"""

from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest
from typing import Dict, Optional
import time


class PrometheusMetrics:
    """Prometheus metrics collector for Ollama Dashboard.

    Exports metrics for:
    - Model operations (start, stop, delete)
    - Retry attempts and success rates
    - Rate limiting events
    - Cache hit/miss rates
    - Request latencies
    """

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """Initialize Prometheus metrics.

        Args:
            registry: Optional custom CollectorRegistry (defaults to default)
        """
        self.registry = registry or CollectorRegistry()
        self._initialize_metrics()

    def _initialize_metrics(self):
        """Initialize all Prometheus metrics."""

        # Model operation counters
        self.model_operations_total = Counter(
            'ollama_model_operations_total',
            'Total model operations',
            ['operation', 'status'],
            registry=self.registry
        )

        # Retry metrics
        self.retry_attempts_total = Counter(
            'ollama_retry_attempts_total',
            'Total retry attempts',
            ['operation'],
            registry=self.registry
        )

        self.retry_successes_total = Counter(
            'ollama_retry_successes_total',
            'Successful retries',
            ['operation'],
            registry=self.registry
        )

        # Rate limit metrics
        self.rate_limit_exceeded_total = Counter(
            'ollama_rate_limit_exceeded_total',
            'Rate limit exceeded events',
            ['operation_type'],
            registry=self.registry
        )

        # Cache metrics
        self.cache_hits_total = Counter(
            'ollama_cache_hits_total',
            'Cache hit count',
            ['cache_type'],
            registry=self.registry
        )

        self.cache_misses_total = Counter(
            'ollama_cache_misses_total',
            'Cache miss count',
            ['cache_type'],
            registry=self.registry
        )

        # Request latency histogram
        self.request_duration_seconds = Histogram(
            'ollama_request_duration_seconds',
            'Request latency in seconds',
            ['operation'],
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0),
            registry=self.registry
        )

        # Gauge metrics
        self.active_models = Gauge(
            'ollama_active_models',
            'Number of currently running models',
            registry=self.registry
        )

        self.available_models = Gauge(
            'ollama_available_models',
            'Number of available models',
            registry=self.registry
        )

        self.rate_limit_remaining = Gauge(
            'ollama_rate_limit_remaining',
            'Remaining requests in rate limit window',
            ['operation_type'],
            registry=self.registry
        )

        self.cache_age_seconds = Gauge(
            'ollama_cache_age_seconds',
            'Age of cached data in seconds',
            ['cache_type'],
            registry=self.registry
        )

        # Health metrics
        self.background_thread_alive = Gauge(
            'ollama_background_thread_alive',
            'Background update thread status (1=alive, 0=dead)',
            registry=self.registry
        )

        self.retry_success_rate = Gauge(
            'ollama_retry_success_rate',
            'Retry success rate (0-100)',
            ['operation'],
            registry=self.registry
        )

        def record_operation(self, operation: str, status: str, duration_seconds: float):
            """Record a model operation.

            Args:
                operation: Operation type (start, stop, delete)
                status: Status (success, failure, timeout)
                duration_seconds: Operation duration
            """
            self.model_operations_total.labels(operation=operation, status=status).inc()
            self.request_duration_seconds.labels(operation=operation).observe(duration_seconds)

        def record_retry_attempt(self, operation: str, success: bool):
            """Record a retry attempt.

            Args:
                operation: Operation being retried
                success: Whether retry was successful
            """
            self.retry_attempts_total.labels(operation=operation).inc()
            if success:
                self.retry_successes_total.labels(operation=operation).inc()

        def record_rate_limit_exceeded(self, operation_type: str):
            """Record a rate limit exceeded event."""
            self.rate_limit_exceeded_total.labels(operation_type=operation_type).inc()

        def record_cache_hit(self, cache_type: str):
            """Record a cache hit."""
            self.cache_hits_total.labels(cache_type=cache_type).inc()

        def record_cache_miss(self, cache_type: str):
            """Record a cache miss."""
            self.cache_misses_total.labels(cache_type=cache_type).inc()

        def update_model_counts(self, active: int, available: int):
            """Update model count gauges."""
            self.active_models.set(active)
            self.available_models.set(available)

        def update_rate_limit_status(self, operation_type: str, remaining: int):
            """Update rate limit remaining requests."""
            self.rate_limit_remaining.labels(operation_type=operation_type).set(remaining)

        def update_cache_age(self, cache_type: str, age_seconds: float):
            """Update cache age metric."""
            self.cache_age_seconds.labels(cache_type=cache_type).set(age_seconds)

        def update_background_thread_status(self, alive: bool):
            """Update background thread status (1=alive, 0=dead)."""
            self.background_thread_alive.set(1 if alive else 0)

        def update_retry_success_rate(self, operation: str, success_rate: float):
            """Update retry success rate (0-100)."""
            self.retry_success_rate.labels(operation=operation).set(success_rate)

        def export_metrics(self) -> bytes:
            """Export metrics in Prometheus format."""
            return generate_latest(self.registry)

    def record_operation(self, operation: str, status: str, duration_seconds: float):
        """Record a model operation.

        Args:
            operation: Operation type (start, stop, delete)
            status: Status (success, failure, timeout)
            duration_seconds: Operation duration
        """
        self.model_operations_total.labels(operation=operation, status=status).inc()
        self.request_duration_seconds.labels(operation=operation).observe(duration_seconds)

    def record_retry_attempt(self, operation: str, success: bool):
        """Record a retry attempt.

        Args:
            operation: Operation being retried
            success: Whether retry was successful
        """
        self.retry_attempts_total.labels(operation=operation).inc()
        if success:
            self.retry_successes_total.labels(operation=operation).inc()

    def record_rate_limit_exceeded(self, operation_type: str):
        """Record a rate limit exceeded event."""
        self.rate_limit_exceeded_total.labels(operation_type=operation_type).inc()

    def record_cache_hit(self, cache_type: str):
        """Record a cache hit."""
        self.cache_hits_total.labels(cache_type=cache_type).inc()

    def record_cache_miss(self, cache_type: str):
        """Record a cache miss."""
        self.cache_misses_total.labels(cache_type=cache_type).inc()

    def update_model_counts(self, active: int, available: int):
        """Update model count gauges."""
        self.active_models.set(active)
        self.available_models.set(available)

    def update_rate_limit_status(self, operation_type: str, remaining: int):
        """Update rate limit remaining requests."""
        self.rate_limit_remaining.labels(operation_type=operation_type).set(remaining)

    def update_cache_age(self, cache_type: str, age_seconds: float):
        """Update cache age metric."""
        self.cache_age_seconds.labels(cache_type=cache_type).set(age_seconds)

    def update_background_thread_status(self, alive: bool):
        """Update background thread status (1=alive, 0=dead)."""
        self.background_thread_alive.set(1 if alive else 0)

    def update_retry_success_rate(self, operation: str, success_rate: float):
        """Update retry success rate (0-100)."""
        self.retry_success_rate.labels(operation=operation).set(success_rate)

    def export_metrics(self) -> bytes:
        """Export metrics in Prometheus format."""
        return generate_latest(self.registry)


# Global Prometheus metrics instance
PROMETHEUS_METRICS = PrometheusMetrics()
