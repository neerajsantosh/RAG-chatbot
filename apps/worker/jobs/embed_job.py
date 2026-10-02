"""Batched embedding job -- NFR-6, phase 3.

Embedding is the throughput-bound step (5k chunks/min/worker) and the one that costs money
per call, so this handler owns batching and rate-limit awareness rather than delegating to
the API.

Phase 3.
"""

from __future__ import annotations

from worker.jobs import Job, JobType, _not_implemented

__all__ = ["handle"]


def handle(job: Job) -> None:
    """Embed pending chunks in batches. Phase 3."""
    if job.type != JobType.EMBED_CHUNKS:
        raise ValueError(f"embed_job cannot handle job type {job.type!r}")
    raise _not_implemented(job, "3")
