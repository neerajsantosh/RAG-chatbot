"""Retention job -- FR-41, NFR-17, phase 5.

Enforces the four retention policies in architecture Â§9.3 across conversations, messages,
traces and tombstones. Phase 5.

The deletion path here deliberately differs from a bulk ``DELETE``: retention runs
periodically against a whole table, so it needs to be batched and restartable to avoid
holding a long transaction against the chat path (NFR-5: analytical work must not contend
with serving).
"""

from __future__ import annotations

from worker.jobs import Job, JobType, _not_implemented

__all__ = ["handle"]


def handle(job: Job) -> None:
    """Apply the retention policy across all four tables. Phase 5."""
    if job.type != JobType.RETENTION_SWEEP:
        raise ValueError(f"retention_job cannot handle job type {job.type!r}")
    raise _not_implemented(job, "5")
