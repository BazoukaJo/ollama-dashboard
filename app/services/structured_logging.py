"""Structured logging utilities for enhanced operational visibility.

Provides:
- JSON structured logging for machine parsing
- Contextual logging with request/operation metadata
- Log level based on operation success/failure
- Integration with Python's logging module
"""

import json
import logging
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs.

    Includes:
    - Timestamp
    - Log level
    - Logger name
    - Message
    - Structured context data
    - Exception info if present
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: LogRecord to format

        Returns:
            JSON string with structured log data
        """
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add structured context if available
        if hasattr(record, 'context'):
            log_data["context"] = record.context

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def create_structured_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """Create a logger with structured JSON formatting.

    Args:
        name: Logger name
        log_file: Optional file to write logs to

    Returns:
        Configured Logger instance
    """
    logger = logging.getLogger(name)

    # Create structured formatter
    formatter = StructuredFormatter()

    # Add stream handler (console)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Add file handler if specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except IOError as e:
            logger.warning(f"Could not create file handler for {log_file}: {e}")

    return logger


def log_operation(
    logger: logging.Logger,
    operation: str,
    success: bool,
    duration_seconds: float,
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> None:
    """Log an operation with structured context.

    Args:
        logger: Logger instance
        operation: Operation name (e.g., 'model_start')
        success: Whether operation succeeded
        duration_seconds: Time taken
        details: Optional additional details
        error: Optional error message
    """
    context = {
        "operation": operation,
        "success": success,
        "duration_seconds": duration_seconds,
    }

    if details:
        context.update(details)

    if error:
        context["error"] = error

    # Create log record with context
    record = logging.LogRecord(
        name=logger.name,
        level=logging.INFO if success else logging.WARNING,
        pathname="",
        lineno=0,
        msg=f"{operation} {'completed' if success else 'failed'}",
        args=(),
        exc_info=None
    )
    record.context = context

    # Log with appropriate level
    if success:
        logger.info(record.getMessage())
    else:
        logger.warning(record.getMessage())


def log_performance_alert(
    logger: logging.Logger,
    operation: str,
    duration_seconds: float,
    threshold_seconds: float
) -> None:
    """Log a performance anomaly/alert.

    Args:
        logger: Logger instance
        operation: Operation name
        duration_seconds: Actual duration
        threshold_seconds: Expected threshold
    """
    severity = "warning" if duration_seconds < threshold_seconds * 2 else "critical"

    context = {
        "alert_type": "performance_anomaly",
        "operation": operation,
        "duration_seconds": duration_seconds,
        "threshold_seconds": threshold_seconds,
        "severity": severity,
    }

    message = (
        f"Performance anomaly: {operation} took {duration_seconds:.2f}s "
        f"(threshold: {threshold_seconds:.2f}s)"
    )

    record = logging.LogRecord(
        name=logger.name,
        level=logging.ERROR if severity == "critical" else logging.WARNING,
        pathname="",
        lineno=0,
        msg=message,
        args=(),
        exc_info=None
    )
    record.context = context

    if severity == "critical":
        logger.error(message)
    else:
        logger.warning(message)
