"""Spans and the attributes every span must carry.

One span tree per question, per architecture §14.1. The stage names below are the
pipeline from architecture §5.2, and they are declared as a constant so that a stage
cannot be renamed in one place and forgotten in another -- and so the trace viewer in
phase 6 has a stable vocabulary to render.

The required-attribute contract is enforced by :func:`Span.validate`, not by convention.
A span that cannot be reproduced later -- because it is missing which prompt version and
which model produced it -- fails validation, because NFR-13 requires that every answer be
reproducible and D9 requires that operators can explain any answer from its trace alone.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Final

from core.clock import Clock, SystemClock
from core.ids import new_id

__all__ = [
    "PIPELINE_STAGES",
    "REQUIRED_SPAN_ATTRIBUTES",
    "Span",
    "SpanRecorder",
    "get_recorder",
    "reset_recorder",
    "span",
]

REQUIRED_SPAN_ATTRIBUTES: Final[tuple[str, ...]] = (
    "config_version",
    "prompt_version",
    "llm_model",
    "tokens_in",
    "tokens_out",
)
"""Attributes every span must carry before it may be exported (NFR-13, D9)."""

PIPELINE_STAGES: Final[tuple[str, ...]] = (
    "auth",
    "context_load",
    "query_rewrite",
    "embed_query",
    "retrieve_dense",
    "retrieve_lexical",
    "fuse",
    "rerank",
    "confidence_gate",
    "context_pack",
    "generate",
    "citation_verify",
    "persist",
)
"""Stage names from architecture §5.2. The trace viewer's vocabulary."""


@dataclass(slots=True)
class Span:
    """One timed unit of work."""

    name: str
    span_id: str = field(default_factory=lambda: new_id("spn_"))
    parent_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    error: dict[str, Any] | None = None

    def set(self, key: str, value: Any) -> None:
        """Record a span attribute. Content-bearing keys are refused, not redacted.

        Refusing rather than redacting is deliberate: a redacted attribute looks
        recorded, so a trace would appear complete while omitting exactly the evidence
        needed to debug it.
        """
        from core.logging.redaction import is_content_field

        if is_content_field(key):
            raise ValueError(
                f"refusing to record content-bearing span attribute {key!r}; "
                "record an id or a score instead"
            )
        self.attributes[key] = value

    def update(self, values: Mapping[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value)

    def fail(self, error: BaseException) -> None:
        code = getattr(error, "code", None)
        self.error = {"type": type(error).__name__, "code": code or "unknown"}

    def validate(self) -> None:
        """Raise unless every required attribute is present.

        ``tokens_in`` and ``tokens_out`` count zero legitimately for a span that calls no
        model, so presence is what is checked, not magnitude.
        """
        missing = [name for name in REQUIRED_SPAN_ATTRIBUTES if name not in self.attributes]
        if missing:
            raise ValueError(f"span {self.name!r} missing required attributes: {missing}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "duration_ms": self.duration_ms,
            "attributes": dict(self.attributes),
            "error": self.error,
        }


class SpanRecorder:
    """Collects completed spans. In-memory in Phase 1; a phase-5 concern to export them."""

    __slots__ = ("_clock", "_spans")

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._spans: list[Span] = []

    def record(self, completed: Span) -> None:
        self._spans.append(completed)

    @property
    def spans(self) -> list[Span]:
        return list(self._spans)

    def by_name(self, name: str) -> list[Span]:
        return [item for item in self._spans if item.name == name]

    def clear(self) -> None:
        self._spans.clear()

    @contextmanager
    def trace(self, name: str, **attributes: Any) -> Iterator[Span]:
        """Time a block of work, recording the span whether or not it succeeds.

        ``validate()`` is *not* called here: stages that legitimately carry no token
        counts are common, and enforcing the contract at export time keeps the fast path
        cheap. See :func:`require_valid_spans`.
        """
        current = Span(name=name)
        current.update(attributes)
        started = self._clock.monotonic()
        try:
            yield current
        except BaseException as exc:
            current.fail(exc)
            raise
        finally:
            current.duration_ms = round((self._clock.monotonic() - started) * 1000, 3)
            self.record(current)

    def require_valid_spans(self) -> None:
        """Validate every recorded span. Called at the export boundary in phase 5."""
        for item in self._spans:
            item.validate()


_recorder = SpanRecorder()


def get_recorder() -> SpanRecorder:
    return _recorder


def reset_recorder() -> None:
    """Replace the process-wide recorder with an empty one. Tests call this."""
    global _recorder
    _recorder = SpanRecorder()


@contextmanager
def span(
    name: str,
    *,
    recorder: SpanRecorder | None = None,
    parent_id: str | None = None,
    **attributes: Any,
) -> Iterator[Span]:
    """Time a block against either an explicit recorder or the process-wide one."""
    active = recorder or get_recorder()
    with active.trace(name, **attributes) as current:
        current.parent_id = parent_id
        yield current


def summarise_stage_latency(stages: Mapping[str, float]) -> dict[str, float]:
    """Reduce a span tree to the per-stage latency shape stored on a trace row.

    Matches the ``stage_latency_ms`` column in architecture §9.1.
    """
    return {name: round(value, 3) for name, value in stages.items() if value is not None}
