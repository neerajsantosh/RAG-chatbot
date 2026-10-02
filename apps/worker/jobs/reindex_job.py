"""Reindex job -- FR-6, phase 2.

Two modes, and the distinction is the whole reason this is a job type rather than an
argument: a full reindex rebuilds every chunk for a document from scratch, while an
incremental one embeds only the chunks whose content hash changed. Running a full reindex
for a one-paragraph edit costs a document's worth of embedding calls for no reason, and
embedding is the bill.

Phase 4 exposes the trigger over the admin API.
"""

from __future__ import annotations

from typing import Final, Literal, cast

from worker.jobs import Job, JobType, _not_implemented

__all__ = ["ReindexMode", "handle", "mode_for"]

ReindexMode = Literal["full", "incremental"]

FULL: Final[str] = "full"
INCREMENTAL: Final[str] = "incremental"


def mode_for(job: Job) -> ReindexMode:
    """Read the mode off the payload, defaulting to ``incremental``.

    The default is the cheap one. Defaulting to ``full`` would mean a producer that forgot
    the field triggers an unbounded embedding bill on every reindex, which is the sort of
    mistake that is only noticed by the finance team.
    """
    raw = job.payload.get("mode", INCREMENTAL)
    if raw not in (FULL, INCREMENTAL):
        raise ValueError(
            f"reindex job {job.job_id!r} has an unknown mode {raw!r}; "
            f"expected {FULL!r} or {INCREMENTAL!r}"
        )
    return cast(ReindexMode, raw)


def handle(job: Job) -> None:
    """Reindex one document, fully or incrementally. Phase 2."""
    if job.type != JobType.REINDEX_DOCUMENT:
        raise ValueError(f"reindex_job cannot handle job type {job.type!r}")
    mode_for(job)  # validate the payload even in phase 1
    raise _not_implemented(job, "2")
