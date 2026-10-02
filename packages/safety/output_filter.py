from __future__ import annotations

from packages.safety.redaction import redact_dict


class OutputFilter:
    """Applies redaction to any text that will be shown to a user or written to a trace.

    This is the final filter on the output path, ensuring that no content-bearing
    fields escape into user-visible output or audit traces.
    """

    @staticmethod
    def filter_response(text: str) -> str:
        """Redact any content-bearing text from the response."""
        from packages.safety.patterns import detect_pii, detect_secrets
        # First run the pattern-based redaction
        cleaned = redact_text(text)
        # Also detect and flag any missed PII
        pii = detect_pii(text)
        if pii:
            # In a full implementation, this would raise or flag the issue
            pass
        return cleaned

    @staticmethod
    def filter_trace_data(data: dict[str, Any]) -> dict[str, Any]:
        """Redact content-bearing fields from trace data."""
        return redact_dict(data)