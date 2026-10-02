"""Job type names and the job envelope.

The plan names six job types across phases 2-5. They are declared in phase 1 because a queue
whose message names are invented by whoever writes the producer first ends up with three
spellings of the same job and a silently unclaimed message.

Each type has a module alongside this one, so the registry in :mod:`worker.consumer` has a
complete mapping from the first commit. A job type with no handler is a loud failure at
startup rather than a message that sits in a queue until somebody notices it never drained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["Job", "JobType"]


class JobType:
    """Job type names as they appear on the wire.

    Constants rather than an enum so the queue payload, which is JSON, and the code that
    handles it agree on spelling without a serialisation step.
    """

    INGEST_DOCUMENT = "ingest_document"
    REINDEX_DOCUMENT = "reindex_document"
    REPROCESS_DOCUMENT = "reprocess_document"
    EMBED_CHUNKS = "embed_chunks"
    PURGE_TOMBSTONED = "purge_tombstoned"
    RETENTION_SWEEP = "retention_sweep"
    FEEDBACK_ANALYSIS = "feedback_analysis"
    EVAL_SWEEP = "eval_sweep"


@dataclass(frozen=True, slots=True)
class Job:
    """A unit of asynchronous work.

    ``attempt`` is incremented by the consumer rather than the producer, but it lives on the
    payload so a dead-lettered message is self-describing: whoever inspects it can see how
    many times it failed without needing the broker's history.
    """

    job_id: str
    type: str
    document_id: str | None = None
    source_id: str | None = None
    attempt: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "type": self.type,
            "document_id": self.document_id,
            "source_id": self.source_id,
            "attempt": self.attempt,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Job:
        """Parse a queue payload, rejecting anything missing a job id or type.

        Malformed messages are rejected rather than coerced. Defaulting ``job_id`` to a
        fresh id would create a message nobody can correlate with its own logs, which is the
        hardest kind of ingestion bug to trace.
        """
        job_id = raw.get("job_id")
        type_ = raw.get("type")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("queue message has no usable 'job_id'")
        if not isinstance(type_, str) or not type_:
            raise ValueError(f"queue message {job_id!r} has no usable 'type'")

        attempt = raw.get("attempt", 0)
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
            raise ValueError(f"queue message {job_id!r} has an invalid 'attempt'")

        payload = raw.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError(f"queue message {job_id!r} has a non-object 'payload'")

        return cls(
            job_id=job_id,
            type=type_,
            document_id=raw.get("document_id"),
            source_id=raw.get("source_id"),
            attempt=attempt,
            payload=payload,
        )
