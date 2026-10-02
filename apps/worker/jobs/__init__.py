"""One module per job type the architecture defines.

Each module owns exactly one job type and exposes a handler. In phase 1 the handlers exist
and raise, because the consumer's registry maps a wire type name to a handler and a
registry with missing entries fails at startup instead of at 3am when a message arrives.

Why they still raise: a handler that returned a fabricated success would let the phase-2
integration tests pass against a worker that does not ingest anything, and the failure would
surface much later as "documents never appear in search".

Import order in this module is load-bearing: :func:`_not_implemented` and the type names are
bound *before* the job modules are imported, because each of those imports them back from
here.
"""

from __future__ import annotations

from worker.jobs.types import Job, JobType


def _not_implemented(job: Job, phase: str) -> NotImplementedError:
    """The single place a phase-1 job handler declines.

    The message names the job, the id and the owning phase, because a worker log line
    reading just "not implemented" is a support ticket rather than a diagnosis.
    """
    return NotImplementedError(
        f"job type {job.type!r} (job_id={job.job_id}) is not implemented until phase {phase}"
    )


from worker.jobs import (  # noqa: E402
    embed_job,
    eval_sweep_job,
    feedback_analysis_job,
    ingest_job,
    purge_job,
    reindex_job,
    reprocess_job,
    retention_job,
)

__all__ = [
    "Job",
    "JobType",
    "_not_implemented",
    "embed_job",
    "eval_sweep_job",
    "feedback_analysis_job",
    "ingest_job",
    "purge_job",
    "reindex_job",
    "reprocess_job",
    "retention_job",
]
