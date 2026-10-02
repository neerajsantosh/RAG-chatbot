"""Reprocess job -- phase 2.

Runs the full pipeline again for a document whose *content* is unchanged but whose derived
state is not: a chunker change, an embedding model change, or an ACL correction. Distinct
from a reindex because the distinction is which side is authoritative, and getting that
backwards either re-fetches documents unnecessarily or fails to rebuild derived state.

Phase 2.
"""

from __future__ import annotations

from worker.jobs import Job, JobType, _not_implemented

__all__ = ["handle"]


def handle(job: Job) -> None:
    """Rebuild derived state for one document without refetching it. Phase 2."""
    if job.type != JobType.REPROCESS_DOCUMENT:
        raise ValueError(f"reprocess_job cannot handle job type {job.type!r}")
    raise _not_implemented(job, "2")
