"""Correlation identifiers.

One idea, deliberately: every request, trace, job and conversation gets an identifier
that appears in logs, spans, database rows and API responses. That is what makes
FR-33 ("every answer traceable within five minutes") achievable, and it is why
identifiers are generated in one place rather than ad hoc at each call site.

Identifiers are opaque strings. They carry no timestamps, no machine names and no
content, so they are safe to log even under the strictest reading of NFR-16.
"""

from __future__ import annotations

import uuid
from typing import Final

__all__ = [
    "HEADER_REQUEST_ID",
    "ID_LENGTH",
    "TRACE_ID_HEADER",
    "new_conversation_id",
    "new_id",
    "new_job_id",
    "new_request_id",
    "new_trace_id",
    "new_user_id",
]

ID_LENGTH: Final = 32
"""Hex length of a generated identifier, without dashes. Short enough for URLs and logs."""

HEADER_REQUEST_ID: Final = "X-Request-Id"
"""Response header echoing the inbound request id, so a user can quote it in a bug report."""

TRACE_ID_HEADER: Final = "X-Trace-Id"
"""SSE `start` event and trace endpoints address traces by this id."""


def new_id(prefix: str = "") -> str:
    """Return a random identifier, optionally namespaced with ``prefix``.

    Random rather than sequential or time-ordered: a time-ordered id leaks request
    volume to anyone who sees one, and a sequential one is guessable. Randomness is
    cheaper to reason about than the alternative.
    """
    raw = uuid.uuid4().hex
    return f"{prefix}{raw[:ID_LENGTH]}" if prefix else raw[:ID_LENGTH]


def new_request_id() -> str:
    return new_id("req_")


def new_trace_id() -> str:
    return new_id("trc_")


def new_job_id() -> str:
    return new_id("job_")


def new_conversation_id() -> str:
    return new_id("cnv_")


def new_user_id() -> str:
    """Only used by the local stub identity provider. Real ids come from the IdP."""
    return new_id("usr_")
