"""Distributed tracing utilities for request tracking and observability.

Provides:
- Request ID generation and propagation
- Trace context management
- Integration with OpenTelemetry patterns
- Request lifecycle tracking
"""

import uuid
import time
from typing import Optional, Dict, Any
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime


# Context variables for trace propagation
_trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')
_span_id_var: ContextVar[str] = ContextVar('span_id', default='')
_request_id_var: ContextVar[str] = ContextVar('request_id', default='')


@dataclass
class TraceContext:
    """Context for distributed tracing.

    Attributes:
        trace_id: Unique trace identifier
        span_id: Unique span identifier
        request_id: HTTP request identifier
        parent_span_id: Optional parent span ID
        start_time: Trace start timestamp
        tags: Custom tags for this trace
    """
    trace_id: str
    span_id: str
    request_id: str
    parent_span_id: Optional[str] = None
    start_time: float = 0.0
    tags: Dict[str, Any] = None

    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()
        if self.tags is None:
            self.tags = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "request_id": self.request_id,
            "parent_span_id": self.parent_span_id,
            "duration_seconds": time.time() - self.start_time,
            "tags": self.tags
        }


class DistributedTracer:
    """Distributed tracing manager for request tracking."""

    @staticmethod
    def create_trace_context(
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        request_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None
    ) -> TraceContext:
        """Create a new trace context.

        Args:
            trace_id: Optional existing trace ID (defaults to new UUID)
            span_id: Optional existing span ID (defaults to new UUID)
            request_id: Optional request ID (defaults to new UUID)
            parent_span_id: Optional parent span ID
            tags: Optional initial tags

        Returns:
            TraceContext instance
        """
        context = TraceContext(
            trace_id=trace_id or str(uuid.uuid4()),
            span_id=span_id or str(uuid.uuid4()),
            request_id=request_id or str(uuid.uuid4()),
            parent_span_id=parent_span_id,
            tags=tags or {}
        )

        # Set context variables for propagation
        _trace_id_var.set(context.trace_id)
        _span_id_var.set(context.span_id)
        _request_id_var.set(context.request_id)

        return context

    @staticmethod
    def get_current_context() -> TraceContext:
        """Get current trace context."""
        return TraceContext(
            trace_id=_trace_id_var.get(),
            span_id=_span_id_var.get(),
            request_id=_request_id_var.get()
        )

    @staticmethod
    def create_child_span(parent_context: TraceContext) -> TraceContext:
        """Create a child span within the same trace.

        Args:
            parent_context: Parent trace context

        Returns:
            Child TraceContext with new span ID
        """
        child = TraceContext(
            trace_id=parent_context.trace_id,
            span_id=str(uuid.uuid4()),
            request_id=parent_context.request_id,
            parent_span_id=parent_context.span_id,
            tags=parent_context.tags.copy()
        )

        _span_id_var.set(child.span_id)
        return child

    @staticmethod
    def add_tag(key: str, value: Any):
        """Add a tag to current trace context."""
        current = DistributedTracer.get_current_context()
        current.tags[key] = value

    @staticmethod
    def get_trace_headers() -> Dict[str, str]:
        """Get trace headers for HTTP propagation.

        Returns:
            Dictionary of headers for trace propagation
        """
        context = DistributedTracer.get_current_context()
        return {
            "X-Trace-ID": context.trace_id,
            "X-Span-ID": context.span_id,
            "X-Request-ID": context.request_id,
        }

    @staticmethod
    def extract_trace_headers(headers: Dict[str, str]) -> Optional[TraceContext]:
        """Extract trace context from HTTP headers.

        Args:
            headers: HTTP headers dictionary

        Returns:
            TraceContext if found, None otherwise
        """
        trace_id = headers.get('X-Trace-ID') or headers.get('x-trace-id')
        span_id = headers.get('X-Span-ID') or headers.get('x-span-id')
        request_id = headers.get('X-Request-ID') or headers.get('x-request-id')

        if trace_id and span_id:
            return DistributedTracer.create_trace_context(
                trace_id=trace_id,
                span_id=span_id,
                request_id=request_id
            )
        return None
