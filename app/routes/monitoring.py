"""Phase 5 monitoring endpoints for performance tracking and metrics."""

from flask import jsonify
from functools import wraps
import time


def create_monitoring_endpoints(bp, ollama_service):
    """Create monitoring and metrics endpoints.

    Args:
        bp: Flask Blueprint
        ollama_service: OllamaService instance
    """

    @bp.route('/api/metrics/performance', methods=['GET'])
    def get_performance_metrics():
        """Get detailed performance metrics and operation statistics.

        Returns:
            JSON with timing stats, success rates, and anomalies
        """
        try:
            stats = ollama_service.get_performance_stats()
            return jsonify({
                "success": True,
                "performance_metrics": stats
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route('/api/metrics/rate-limits', methods=['GET'])
    def get_rate_limits():
        """Get current rate limit status.

        Returns:
            JSON with remaining requests per operation type
        """
        try:
            limits = ollama_service.get_rate_limit_status()
            return jsonify({
                "success": True,
                "rate_limits": limits
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route('/api/metrics/summary', methods=['GET'])
    def get_metrics_summary():
        """Get summary of all monitoring metrics.

        Returns:
            JSON with health, performance, and rate limit summary
        """
        try:
            health = ollama_service.get_component_health()
            performance = ollama_service.get_performance_stats()
            rate_limits = ollama_service.get_rate_limit_status()

            return jsonify({
                "success": True,
                "summary": {
                    "health": health,
                    "performance": performance,
                    "rate_limits": rate_limits,
                    "timestamp": time.time()
                }
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    return bp
