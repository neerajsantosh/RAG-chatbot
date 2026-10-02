"""Ingestion worker.

Phase 1 runs the queue loop with no jobs to consume. See :mod:`worker.main` for the
behaviours that are already real: interruptible polling, finishing in-flight work on
shutdown, and not dying on the first failing job.
"""

from worker.jobs import Job, JobType
from worker.main import JobHandler, Worker, WorkerStats, main

__all__ = ["Job", "JobHandler", "JobType", "Worker", "WorkerStats", "main"]
