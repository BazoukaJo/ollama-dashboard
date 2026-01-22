"""Alerting system for operational alerts and notifications.

Provides:
- Alert manager for creating and tracking alerts
- Multiple alert severity levels
- Webhook integration for external notification
- Alert deduplication and history
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from collections import deque
import threading
import json
import requests


@dataclass
class Alert:
    """Alert definition.

    Attributes:
        id: Unique alert identifier
        title: Alert title
        description: Detailed description
        severity: Alert severity (info, warning, critical)
        source: Alert source (e.g., 'retry_failure', 'rate_limit')
        timestamp: When alert was created
        resolved: Whether alert is resolved
        tags: Alert tags for filtering
    """
    id: str
    title: str
    description: str
    severity: str  # info, warning, critical
    source: str
    timestamp: str
    resolved: bool = False
    tags: Dict[str, str] = None

    def to_dict(self) -> Dict:
        """Convert alert to dictionary."""
        data = asdict(self)
        if self.tags is None:
            data['tags'] = {}
        return data


class AlertManager:
    """Manages alerts and notifications.

    Features:
    - Create and track alerts
    - Webhook integration for external services
    - Alert deduplication
    - History management
    - Severity-based routing
    """

    def __init__(self, max_alerts: int = 100, webhook_url: Optional[str] = None):
        """Initialize alert manager.

        Args:
            max_alerts: Maximum alerts to keep in history
            webhook_url: Optional webhook URL for notifications
        """
        self.max_alerts = max_alerts
        self.webhook_url = webhook_url
        self.alerts: deque = deque(maxlen=max_alerts)
        self.alert_count = 0
        self.lock = threading.Lock()
        self.handlers: Dict[str, List[Callable]] = {
            'info': [],
            'warning': [],
            'critical': []
        }

    def create_alert(
        self,
        title: str,
        description: str,
        severity: str,
        source: str,
        tags: Optional[Dict[str, str]] = None
    ) -> Alert:
        """Create and register an alert.

        Args:
            title: Alert title
            description: Alert description
            severity: Severity level (info, warning, critical)
            source: Alert source identifier
            tags: Optional tags for the alert

        Returns:
            Created Alert instance
        """
        with self.lock:
            self.alert_count += 1
            alert = Alert(
                id=f"alert_{self.alert_count}",
                title=title,
                description=description,
                severity=severity,
                source=source,
                timestamp=datetime.now().isoformat(),
                tags=tags or {}
            )

            self.alerts.append(alert)

            # Trigger handlers
            self._trigger_handlers(severity, alert)

            # Send webhook if configured
            if self.webhook_url:
                self._send_webhook(alert)

            return alert

    def _trigger_handlers(self, severity: str, alert: Alert):
        """Trigger registered handlers for alert severity."""
        handlers = self.handlers.get(severity, [])
        for handler in handlers:
            try:
                handler(alert)
            except Exception as e:
                # Log handler error but don't fail
                pass

    def _send_webhook(self, alert: Alert):
        """Send alert to webhook endpoint."""
        try:
            payload = alert.to_dict()
            headers = {'Content-Type': 'application/json'}

            requests.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=5
            )
        except Exception as e:
            # Log webhook error but don't fail
            pass

    def resolve_alert(self, alert_id: str):
        """Mark an alert as resolved."""
        with self.lock:
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.resolved = True
                    break

    def get_alerts(
        self,
        severity: Optional[str] = None,
        source: Optional[str] = None,
        resolved: Optional[bool] = None
    ) -> List[Alert]:
        """Get alerts matching criteria.

        Args:
            severity: Optional severity filter
            source: Optional source filter
            resolved: Optional resolution status filter

        Returns:
            List of matching alerts
        """
        with self.lock:
            alerts = list(self.alerts)

        # Filter alerts
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if source:
            alerts = [a for a in alerts if a.source == source]
        if resolved is not None:
            alerts = [a for a in alerts if a.resolved == resolved]

        return alerts

    def register_handler(self, severity: str, handler: Callable):
        """Register a handler for alerts of specific severity.

        Args:
            severity: Severity level (info, warning, critical)
            handler: Callable that receives Alert instance
        """
        if severity not in self.handlers:
            self.handlers[severity] = []
        self.handlers[severity].append(handler)

    def get_recent_alerts(self, limit: int = 20) -> List[Alert]:
        """Get recent alerts.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of recent alerts (newest first)
        """
        with self.lock:
            alerts = list(self.alerts)
        return list(reversed(alerts))[:limit]

    def get_unresolved_count(self) -> int:
        """Get count of unresolved alerts."""
        return len([a for a in self.get_alerts(resolved=False)])

    def get_critical_count(self) -> int:
        """Get count of critical unresolved alerts."""
        return len([a for a in self.get_alerts(severity='critical', resolved=False)])


# Global alert manager
ALERT_MANAGER = AlertManager()


class AlertThresholds:
    """Threshold-based alert configuration.

    Defines thresholds for automatic alert generation.
    """

    # Retry failure threshold (% failures)
    RETRY_FAILURE_THRESHOLD = 50.0

    # Rate limit threshold (events per minute)
    RATE_LIMIT_THRESHOLD = 3

    # Cache hit ratio threshold (% hits)
    CACHE_HIT_THRESHOLD = 70.0

    # Background thread failure threshold (consecutive failures)
    BACKGROUND_THREAD_THRESHOLD = 5

    # Slow operation threshold (seconds)
    SLOW_OPERATION_THRESHOLD = 30.0

    # Model operation timeout threshold (seconds)
    MODEL_OPERATION_TIMEOUT = 60.0
