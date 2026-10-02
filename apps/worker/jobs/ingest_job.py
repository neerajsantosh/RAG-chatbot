"""Ingestion job -- FR-4, phase 2.

The pipeline this handler will own: fetch the document, normalise, chunk, embed, index, and
make the result visible atomically. Phase 2.

The phase 2 implementation has to honour the idempotency rule from architecture Â§9:
re-running the same document is a no-op, keyed on ``content_hash``. A re-delivered queue
message is the normal case, not an error, because the queue is at-least-once.
"""

from __future__ import annotations

from worker.jobs import Job, JobType, _not_implemented

__all__ = ["handle"]


def handle(job: Job) -> None:
    """Ingest one document. Phase 2."""
    if job.type != JobType.INGEST_DOCUMENT:
        raise ValueError(f"ingest_job cannot handle job type {job.type!r}")
    raise _not_implemented(job, "2")
