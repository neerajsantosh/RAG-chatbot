"""Tracing surface.

Phase 1 ships a span recorder rather than a full OpenTelemetry pipeline. The reason is
the shape of the required attributes, not a preference for less: architecture §14.1
requires that *every* span carry config version, prompt version, model, tokens and cost.
Enforcing that here, with a single recorder the tests can assert against, is more useful
than an exporter wired up before any span exists. Phase 5 is where this is expected to
grow into real OTel export.
"""

from core.telemetry.spans import (
    REQUIRED_SPAN_ATTRIBUTES,
    Span,
    SpanRecorder,
    get_recorder,
    reset_recorder,
    span,
)

__all__ = [
    "REQUIRED_SPAN_ATTRIBUTES",
    "Span",
    "SpanRecorder",
    "get_recorder",
    "reset_recorder",
    "span",
]
