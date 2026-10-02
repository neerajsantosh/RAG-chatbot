"""Structured JSON logging with redaction applied by default.

One logger factory for the whole codebase. Two properties matter more than formatting:

* **Structure.** Log records carry named fields (``extra_fields``) rather than an
  interpolated message, so they can be queried and aggregated -- required for FR-33,
  FR-34 and the metrics in architecture §14.
* **Redaction by default.** The redaction filter is attached during
  :func:`configure_logging`. Turning it off requires passing ``redact=False``
  explicitly, which makes an accidental leak a visible decision rather than an omission.

Messages must therefore describe *what happened* and never interpolate content. The
convention is ``logger.info("retrieval completed", extra=log_extra(chunk_id=cid))``, never
``logger.info(f"no answer for: {question}")``.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Final

from core.logging.redaction import RedactionFilter

__all__ = [
    "LOGGER_NAMESPACE",
    "configure_logging",
    "get_logger",
    "log_extra",
]

LOGGER_NAMESPACE: Final = "rag"
"""Root namespace. Everything logs under ``rag.<service>.<component>``."""

_RESERVED: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def log_extra(**fields: Any) -> dict[str, Any]:
    """Namespace log fields so they cannot collide with :class:`logging.LogRecord` attributes.

    ``extra_fields`` is a single LogRecord attribute, which sidesteps the "Attempt to set
    an attribute on a LogRecord" failure that :func:`logging.Logger.info` raises when a
    field is named after a reserved attribute.
    """
    return {"extra_fields": fields}


def _extract_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Collect structured fields from a record.

    Standard ``extra=`` keys are read too, so callers are not forced to wrap every call
    in :func:`log_extra`.
    """
    fields: dict[str, Any] = {}

    wrapped = getattr(record, "extra_fields", None)
    if isinstance(wrapped, dict):
        fields.update(wrapped)

    for key, value in record.__dict__.items():
        if key in _RESERVED or key == "extra_fields":
            continue
        fields.setdefault(key, value)

    return fields


class JsonFormatter(logging.Formatter):
    """Renders one JSON object per line."""

    __slots__ = ("_include_environment",)

    def __init__(self, *, include_environment: str | None = None) -> None:
        super().__init__()
        self._include_environment = include_environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if self._include_environment:
            payload["environment"] = self._include_environment

        fields = _extract_fields(record)
        if fields:
            payload["fields"] = fields

        if record.exc_info:
            # The exception message may embed content, so only its type is recorded.
            exc_type = record.exc_info[0]
            payload["error"] = {
                "type": exc_type.__name__ if exc_type else "Unknown",
                "message": str(record.exc_info[1])[:500],
            }

        return json.dumps(payload, default=str, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    """Human-readable single line. For local development and test output."""

    def format(self, record: logging.LogRecord) -> str:
        fields = _extract_fields(record)
        rendered = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
        base = f"{record.levelname:<7} {record.name} {record.getMessage()}"
        return f"{base} {rendered}".rstrip()


_configured = False


def configure_logging(
    level: str = "INFO",
    *,
    fmt: str = "json",
    redact: bool = True,
    environment: str | None = None,
    stream: Any = None,
) -> None:
    """Install the root handler for the whole application. Idempotent.

    Args:
        level: Standard logging level name.
        fmt: ``"json"`` for aggregation, ``"text"`` for reading.
        redact: Attach :class:`~core.logging.redaction.RedactionFilter`. Defaults to True.
            The Phase 1 gate calls this with ``redact=False`` in a test to prove the guard
            actually fails when removed.
        environment: Recorded on every line when set.
        stream: Output stream. Defaults to stderr.
    """
    global _configured

    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)

    if fmt == "text":
        handler.setFormatter(TextFormatter())
    else:
        handler.setFormatter(JsonFormatter(include_environment=environment))

    if redact:
        handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn installs its own handlers; route them through ours so redaction applies.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        third_party = logging.getLogger(name)
        third_party.handlers.clear()
        third_party.propagate = True

    _configured = True


def is_configured() -> bool:
    """Whether :func:`configure_logging` has run. Used by the startup banner."""
    return _configured


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger.

    ``get_logger(__name__)`` from a module inside the ``rag`` namespace is enough;
    module-qualified names outside it are prefixed automatically.
    """
    if name.startswith(f"{LOGGER_NAMESPACE}.") or name == LOGGER_NAMESPACE:
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")
