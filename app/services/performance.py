"""Performance monitoring and rate limiting utilities for Ollama Dashboard.

Provides:
- Request rate limiting to prevent Ollama overload
- Performance metrics collection and tracking
- Request/response timing analysis
- Performance alerts and thresholds
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta
import threading
import time
from typing import Dict, List, Optional, Tuple


class RateLimiter:
    """Token bucket rate limiter for controlling request frequency.

    Prevents overwhelming Ollama service by limiting:
    - Model operations (start, stop, delete)
    - Model pull requests
    - Background update frequency
    """

    def __init__(self, max_requests: int, window_seconds: int):
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()
        self.lock = threading.Lock()

    def allow_request(self) -> bool:
        """Check if request is allowed under rate limit.

        Returns:
            True if request allowed, False if rate limit exceeded
        """
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)

        with self.lock:
            # Remove old requests outside window
            while self.requests and self.requests[0] < cutoff:
                self.requests.popleft()

            # Check if we can add new request
            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True
            return False

    def get_remaining_requests(self) -> int:
        """Get number of requests remaining in current window."""
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.window_seconds)

        with self.lock:
            # Count requests in current window
            active = sum(1 for t in self.requests if t >= cutoff)
            return max(0, self.max_requests - active)


class PerformanceMetrics:
    """Track performance metrics for monitoring and optimization.

    Tracks:
    - Request timing (min, max, avg)
    - Operation success/failure rates
    - Resource usage patterns
    - Performance anomalies
    """

    def __init__(self, window_size: int = 100):
        """Initialize performance metrics.

        Args:
            window_size: Number of recent operations to track
        """
        self.window_size = window_size
        self.lock = threading.Lock()

        # Request timing metrics (operation_type -> [durations])
        self.operation_timings: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

        # Operation counters
        self.operation_counts: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"success": 0, "failure": 0, "total": 0}
        )

        # Performance alerts
        self.performance_alerts: deque = deque(maxlen=50)

        # Thresholds for alerts (in seconds)
        self.thresholds = {
            "model_start": 30.0,  # Model start should complete within 30s
            "model_stop": 5.0,    # Model stop should be quick
            "model_delete": 10.0, # Delete should complete within 10s
            "background_update": 5.0,  # Background updates should be quick
        }

    def record_operation(
        self,
        operation_type: str,
        duration_seconds: float,
        success: bool = True
    ) -> None:
        """Record an operation's timing and result.

        Args:
            operation_type: Type of operation (e.g., 'model_start')
            duration_seconds: Time taken in seconds
            success: Whether operation succeeded
        """
        with self.lock:
            # Record timing
            self.operation_timings[operation_type].append(duration_seconds)

            # Update counters
            counts = self.operation_counts[operation_type]
            counts["total"] += 1
            if success:
                counts["success"] += 1
            else:
                counts["failure"] += 1

            # Check for performance anomalies
            threshold = self.thresholds.get(operation_type, 60.0)
            if duration_seconds > threshold:
                alert = {
                    "timestamp": datetime.now().isoformat(),
                    "operation": operation_type,
                    "duration": duration_seconds,
                    "threshold": threshold,
                    "severity": "warning" if duration_seconds < threshold * 2 else "critical"
                }
                self.performance_alerts.append(alert)

    def get_operation_stats(self, operation_type: str) -> Dict:
        """Get statistics for an operation type.

        Returns:
            Dict with timing stats and success rates
        """
        with self.lock:
            timings = list(self.operation_timings.get(operation_type, []))
            counts = self.operation_counts.get(operation_type, {})

            if not timings:
                return {
                    "operation": operation_type,
                    "total_operations": 0,
                    "success_rate": 0.0,
                    "timing_stats": None
                }

            total = counts.get("total", 0)
            success = counts.get("success", 0)

            return {
                "operation": operation_type,
                "total_operations": total,
                "success_count": success,
                "failure_count": counts.get("failure", 0),
                "success_rate": (success / total * 100) if total > 0 else 0.0,
                "timing_stats": {
                    "min_seconds": min(timings),
                    "max_seconds": max(timings),
                    "avg_seconds": sum(timings) / len(timings),
                    "median_seconds": sorted(timings)[len(timings) // 2],
                    "recent_count": len(timings)
                }
            }

    def get_all_stats(self) -> Dict:
        """Get statistics for all tracked operations."""
        with self.lock:
            operations = list(self.operation_counts.keys())

        return {
            "operations": [self.get_operation_stats(op) for op in operations],
            "recent_alerts": list(self.performance_alerts)[-10:],  # Last 10 alerts
        }

    def get_anomalies(self) -> List[Dict]:
        """Get recent performance anomalies/alerts."""
        with self.lock:
            return list(self.performance_alerts)[-20:]  # Last 20 alerts


# Global rate limiters for different operation types
RATE_LIMITERS = {
    "model_operations": RateLimiter(max_requests=5, window_seconds=60),  # 5 ops/min
    "model_pull": RateLimiter(max_requests=2, window_seconds=300),  # 2 pulls/5min
    "background_updates": RateLimiter(max_requests=6, window_seconds=60),  # 6 updates/min
}

# Global performance metrics
PERFORMANCE_METRICS = PerformanceMetrics(window_size=100)
