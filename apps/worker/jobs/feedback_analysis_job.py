"""Feedback analysis job -- phase 5.

Clusters downvotes and refusals into retrieval failures, prompt failures and content gaps,
so the weekly triage in architecture Â§9 is generated rather than assembled by hand.

Phase 5.
"""

from __future__ import annotations

from worker.jobs import Job, JobType, _not_implemented

__all__ = ["handle"]


def handle(job: Job) -> None:
    """Cluster feedback into actionable failure categories. Phase 5."""
    if job.type != JobType.FEEDBACK_ANALYSIS:
        raise ValueError(f"feedback_analysis_job cannot handle job type {job.type!r}")
    raise _not_implemented(job, "5")
