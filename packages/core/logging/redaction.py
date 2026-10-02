"""Log redaction -- the mechanism behind NFR-16.

NFR-16 says no document content and no user question text may appear in application logs.
That rule is easy to state and easy to violate by accident, six months in, by one
``logger.info(f"got question: {question}")``. So it is enforced here rather than trusted
to reviewer diligence.

Strategy: **default deny.** A field is emitted only if it is on the allow-list. Everything
else is replaced by a type summary (``<str len=412>``), which keeps logs useful for
debugging shapes without keeping the text. The content deny-list is applied *before* the
allow-list, so a field that is both informative and dangerous still loses its value.

Two-layer design:

* ``CONTENT_FIELD_NAMES`` and ``CONTENT_MARKERS`` catch anything resembling corpus or
  user text, including under an unexpected key.
* ``SAFE_FIELD_NAMES`` explicitly permits the identifiers, counts, scores, versions,
  durations and statuses that make logs worth reading.

If a legitimate field keeps getting redacted, add it to ``SAFE_FIELD_NAMES`` in review.
Widening the allow-list is visible in a diff; loosening the deny-list is not, so prefer
the former.
"""

from __future__ import annotations

import re
from typing import Any, Final

__all__ = [
    "CONTENT_FIELD_NAMES",
    "CONTENT_MARKERS",
    "REDACTED",
    "SAFE_FIELD_NAMES",
    "RedactionFilter",
    "is_content_field",
    "is_safe_field",
    "redact_mapping",
    "redact_value",
]

REDACTED: Final = "[redacted]"
"""Placeholder written in place of a content field's value."""

CONTENT_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "answer",
        "answertext",
        "body",
        "bodytext",
        "chunk",
        "chunktext",
        "chunks",
        "completion",
        "content",
        "context",
        "contexttext",
        "document",
        "documenttext",
        "excerpt",
        "headingpath",
        "message",
        "messages",
        "passage",
        "passages",
        "prompt",
        "query",
        "querytext",
        "question",
        "retrievedtext",
        "snippet",
        "text",
        "transcript",
    }
)
"""Exact field names that must never carry their value. Compared after normalisation."""

CONTENT_MARKERS: Final[tuple[str, ...]] = (
    "answer",
    "answertext",
    "bodytext",
    "chunktext",
    "completion",
    "documenttext",
    "passage",
    "prompttext",
    "question",
    "snippet",
    "transcript",
)
"""Substrings that mark a field as content-bearing even under an unexpected key."""

SAFE_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        # identifiers -- the whole point of FR-33
        "requestid",
        "traceid",
        "conversationid",
        "messageid",
        "sourceid",
        "documentid",
        "chunkid",
        "jobid",
        "eventid",
        "parentid",
        # correlation and routing
        "service",
        "environment",
        "component",
        "method",
        "path",
        "route",
        "status",
        "statuscode",
        "errorcode",
        "errortype",
        # versions -- NFR-13
        "configversion",
        "promptversion",
        "chunkerversion",
        "chatmodel",
        "embeddingmodel",
        "embeddingmodelversion",
        "llmmodel",
        "llmmodelversion",
        "rerankermodel",
        # counts
        "count",
        "counts",
        "total",
        "chunksfound",
        "chunksadmitted",
        "documents",
        "candidates",
        "topk",
        "reranktopn",
        "tokensin",
        "tokensout",
        "attempt",
        "attempts",
        # scores and decisions
        "score",
        "scores",
        "rerankscore",
        "fusedscore",
        "threshold",
        "refused",
        "decision",
        "reason",
        # durations -- NFR-1
        "durationms",
        "ttftms",
        "totalms",
        "latencyms",
        "stagelatencyms",
        "stagems",
        "elapsedms",
        # cost -- NFR-19
        "costusd",
        "cost",
        "tokensperanswer",
        # dataset / eval
        "dataset",
        "datasetname",
        "datasetversion",
        "metric",
        "metricname",
        "value",
        "baseline",
        "numquestions",
        "recall",
        "recallat",
        "mrr",
        "ndcg",
        "hitrate",
        "groundedness",
        # redaction
        "redactedcount",
        "redactedfields",
    }
)
"""Fields permitted to keep their exact value."""

_NON_ALNUM: Final = re.compile(r"[^a-z0-9]+")
_MAX_DEPTH: Final = 6
"""Recursion limit for nested structures. Deeper values are summarised, not walked."""


def _normalise(name: str) -> str:
    return _NON_ALNUM.sub("", name.strip().lower())


def is_content_field(name: str, *, extra_safe: frozenset[str] | None = None) -> bool:
    """Whether ``name`` names a field whose value must never be logged.

    Deny rules are evaluated first, so a field that is both informative and dangerous
    loses its value.

    Args:
        name: The field name as written at the call site.
        extra_safe: Additional field names to permit for this call, already normalised.
    """
    normalised = _normalise(name)
    if normalised in CONTENT_FIELD_NAMES:
        return True
    if _is_safe_field(normalised, extra_safe=extra_safe):
        return False
    return any(marker in normalised for marker in CONTENT_MARKERS)


def _is_safe_field(normalised: str, *, extra_safe: frozenset[str] | None = None) -> bool:
    if normalised in SAFE_FIELD_NAMES:
        return True
    return extra_safe is not None and normalised in extra_safe


def is_safe_field(name: str, *, extra_safe: frozenset[str] | None = None) -> bool:
    """Whether ``name`` is explicitly permitted to keep its exact value."""
    return _is_safe_field(_normalise(name), extra_safe=extra_safe)


def redact_value(value: Any, *, depth: int = 0) -> Any:
    """Summarise a value by type, without keeping its content.

    Strings become a length marker, bytes and sequences a count, everything else its type
    name. This is what makes default-deny tolerable: unknown fields still tell you
    whether something was populated.
    """
    if depth > _MAX_DEPTH:
        return "<max-depth>"
    if value is None:
        return None
    if isinstance(value, str):
        return f"<str len={len(value)}>"
    if isinstance(value, bytes | bytearray):
        return f"<bytes len={len(value)}>"
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, dict):
        return redact_mapping(value, depth=depth + 1)
    if isinstance(value, list | tuple | set | frozenset):
        return f"<{type(value).__name__} len={len(value)}>"
    return f"<{type(value).__name__}>"


def redact_mapping(
    mapping: dict[str, Any],
    *,
    extra_safe: frozenset[str] | None = None,
    depth: int = 0,
) -> dict[str, Any]:
    """Return a copy of ``mapping`` safe to log.

    Three outcomes per field:

    * content-bearing -> :data:`REDACTED`, keeping the key so a reader can tell the field
      was populated rather than never set;
    * explicitly allow-listed -> the value verbatim, since that is what makes the
      allow-list useful (ids, versions, scores, durations);
    * everything else -> a type summary, because unknown fields must not become a way to
      smuggle content past the deny-list under an unexpected name.
    """
    result: dict[str, Any] = {}

    for key, value in mapping.items():
        normalised = _normalise(key)
        if normalised in CONTENT_FIELD_NAMES or any(
            marker in normalised for marker in CONTENT_MARKERS
        ):
            result[key] = REDACTED
        elif _is_safe_field(normalised, extra_safe=extra_safe):
            result[key] = value
        else:
            result[key] = redact_value(value, depth=depth + 1)

    return result


class RedactionFilter:
    """Logging filter that rewrites content-bearing fields before emission.

    Attach to a handler or a logger. :mod:`core.logging.logger` attaches it by default;
    it is optional only so that the Phase 1 gate can prove the guard actually fails when
    it is removed.
    """

    __slots__ = ("_extra_safe",)

    def __init__(self, *, extra_safe: frozenset[str] | None = None) -> None:
        self._extra_safe = frozenset(_normalise(name) for name in (extra_safe or ()))

    def filter(self, record: Any) -> bool:
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            record.extra_fields = redact_mapping(extra, extra_safe=self._extra_safe)
        elif extra is not None:
            record.extra_fields = redact_value(extra)
        return True
