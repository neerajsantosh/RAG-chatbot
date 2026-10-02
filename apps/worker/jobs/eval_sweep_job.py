"""Eval sweep job -- NFR-12, phase 5.

Runs the eval harness over the golden dataset on a schedule so the regression gate sees
model, prompt or retrieval changes as they land rather than when somebody remembers to
re-run it.

Phase 5. This is the job that makes ``evals/baselines/`` a live artifact instead of a
committed number nobody trusts.
"""

from __future__ import annotations

from worker.jobs import Job, JobType, _not_implemented

__all__ = ["handle"]


def handle(job: Job) -> None:
    """Run the golden eval and compare against the stored baseline. Phase 5."""
    if job.type != JobType.EVAL_SWEEP:
        raise ValueError(f"eval_sweep_job cannot handle job type {job.type!r}")
    raise _not_implemented(job, "5")
