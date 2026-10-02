"""Logging surface.

Note for readers: this package is ``core.logging``, not the standard library's
``logging``. Python 3 absolute imports mean ``import logging`` anywhere in this package
still resolves to the standard library -- but always import this package as
``core.logging``.
"""

from core.logging.logger import (
    configure_logging,
    get_logger,
    is_configured,
    log_extra,
)
from core.logging.redaction import (
    CONTENT_FIELD_NAMES,
    REDACTED,
    SAFE_FIELD_NAMES,
    RedactionFilter,
    is_content_field,
    is_safe_field,
    redact_mapping,
    redact_value,
)

__all__ = [
    "CONTENT_FIELD_NAMES",
    "REDACTED",
    "SAFE_FIELD_NAMES",
    "RedactionFilter",
    "configure_logging",
    "get_logger",
    "is_configured",
    "is_content_field",
    "is_safe_field",
    "log_extra",
    "redact_mapping",
    "redact_value",
]
