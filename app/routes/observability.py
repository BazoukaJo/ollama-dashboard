"""Phase 6 observability endpoints for metrics, tracing, and alerts."""

from flask import Response, jsonify
## Prometheus metrics import removed
from app.services.alerting import ALERT_MANAGER


def create_observability_endpoints(bp, ollama_service):
    """Create observability and integration endpoints.

    Args:
        bp: Flask Blueprint
        ollama_service: OllamaService instance
    """

    # Prometheus metrics endpoint removed

    @bp.route('/api/observability/alerts', methods=['GET'])
    def get_alerts():
        """Get current alerts.

        Query parameters:
        - severity: Filter by severity (info, warning, critical)
        - source: Filter by source
        - unresolved: Filter unresolved only (true/false)

        Returns:
            JSON with alert list
        """
        try:
            from flask import request

            severity = request.args.get('severity')
            source = request.args.get('source')
            unresolved = request.args.get('unresolved', '').lower() == 'true'

            resolved = None if not unresolved else False

            alerts = ALERT_MANAGER.get_alerts(
                severity=severity,
                source=source,
                resolved=resolved
            )

            return jsonify({
                "success": True,
                "alerts": [a.to_dict() for a in alerts],
                "total": len(alerts),
                "unresolved_count": ALERT_MANAGER.get_unresolved_count(),
                "critical_count": ALERT_MANAGER.get_critical_count()
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route('/api/observability/alerts/recent', methods=['GET'])
    def get_recent_alerts():
        """Get recent alerts.

        Returns:
            JSON with recent alerts (newest first)
        """
        try:
            from flask import request
            limit = int(request.args.get('limit', 20))

            alerts = ALERT_MANAGER.get_recent_alerts(limit=limit)

            return jsonify({
                "success": True,
                "alerts": [a.to_dict() for a in alerts],
                "total": len(alerts),
                "unresolved_count": ALERT_MANAGER.get_unresolved_count(),
                "critical_count": ALERT_MANAGER.get_critical_count()
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route('/api/observability/alerts/summary', methods=['GET'])
    def get_alerts_summary():
        """Get alerts summary.

        Returns:
            JSON with alert counts and status
        """
        try:
            by_severity = {
                'info': len(ALERT_MANAGER.get_alerts(severity='info')),
                'warning': len(ALERT_MANAGER.get_alerts(severity='warning')),
                'critical': len(ALERT_MANAGER.get_alerts(severity='critical'))
            }

            return jsonify({
                "success": True,
                "summary": {
                    "total_alerts": len(ALERT_MANAGER.alerts),
                    "unresolved_count": ALERT_MANAGER.get_unresolved_count(),
                    "critical_count": ALERT_MANAGER.get_critical_count(),
                    "by_severity": by_severity,
                    "recent_alerts": [a.to_dict() for a in ALERT_MANAGER.get_recent_alerts(5)]
                }
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @bp.route('/api/observability/alerts/<alert_id>/resolve', methods=['POST'])
    def resolve_alert(alert_id):
        """Resolve an alert.

        Args:
            alert_id: Alert ID to resolve

        Returns:
            JSON confirmation
        """
        try:
            ALERT_MANAGER.resolve_alert(alert_id)

            return jsonify({
                "success": True,
                "message": f"Alert {alert_id} resolved"
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    return bp
