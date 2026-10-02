"""Purge job -- FR-41, phase 3.

Deletion is tombstone-first then asynchronous purge (architecture Â§9): the tombstone makes
content disappear from results immediately, and this job physically removes the rows once
the retention window allows. Keeping those two steps separate is what lets a delete be
immediate without pretending a hard delete is instant.

Phase 3.
"""

from __future__ import annotations

from worker.jobs import Job, JobType, _not_implemented

__all__ = ["handle"]


def handle(job: Job) -> None:
    """Purge tombstoned rows past their retention window. Phase 3."""
    if job.type != JobType.PURGE_TOMBSTONED:
        raise ValueError(f"purge_job cannot handle job type {job.type!r}")
    raise _not_implemented(job, "3")
