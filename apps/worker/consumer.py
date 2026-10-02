"""Queue consumer skeleton: poll, acknowledge, retry, dead-letter.

The state machine is real in phase 1; only the broker is missing. That split is
deliberate -- retry and dead-letter policy is where silent data loss hides, and it should
be decided and tested before a queue exists, not discovered when messages vanish.

The contract every handler must satisfy:

**At-least-once delivery means handlers must be idempotent.** A message can be delivered
twice and the second delivery is not an error. This is why ingestion is keyed on
``content_hash`` (architecture §9). The consumer does not try to prevent redelivery; no
consumer can.

**A handler exception never acknowledges the message.** The only two exits are "handled"
and "moved to the dead-letter queue". A consumer that catches an error, logs it and
acknowledges is a consumer that drops work, and the log is the only evidence.

**Retry is bounded and then dead-lettered.** ``max_attempts`` exists so a poison message
cannot occupy a worker slot forever. The default of 5 is a placeholder to be tuned against
real failure distributions in phase 2, not a considered number.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from core.errors import AppError
from core.logging import get_logger, log_extra
from worker.jobs import Job
from worker.jobs import embed_job as _embed_job
from worker.jobs import eval_sweep_job as _eval_sweep_job
from worker.jobs import feedback_analysis_job as _feedback_analysis_job
from worker.jobs import ingest_job as _ingest_job
from worker.jobs import purge_job as _purge_job
from worker.jobs import reindex_job as _reindex_job
from worker.jobs import reprocess_job as _reprocess_job
from worker.jobs import retention_job as _retention_job

__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "DeadLetter",
    "Handler",
    "JobSource",
    "RetryDecision",
    "build_registry",
    "consumer_retry_sleep",
    "decide",
    "unclaimed_types",
]

_logger = get_logger(__name__)

DEFAULT_MAX_ATTEMPTS = 5


class JobSource(Protocol):
    """The broker, as the consumer needs it.

    Two methods, because "fetch" and "acknowledge" are genuinely different operations
    against every queue: acknowledging is what tells the broker the message is done, and
    getting it wrong in either direction means at-least-once becoming at-most-once or
    at-lever-once.
    """

    def poll(self, *, limit: int, timeout: float) -> Iterable[Job]:
        """Return up to ``limit`` jobs, waiting at most ``timeout`` seconds."""

    def acknowledge(self, job: Job) -> None:
        """Tell the broker this job is complete."""


Handler = Callable[[Job], None]

#: Wire type name -> handler. Built by :func:`build_registry`; see that function's note on
#: completeness at startup.
_REGISTRY: dict[str, Handler] = {}


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """What to do with a job that failed."""

    retry: bool
    dead_letter: bool
    next_attempt: int
    reason: str


@dataclass(frozen=True, slots=True)
class DeadLetter:
    """A job that exhausted its attempts, with the failure that stopped it."""

    job: Job
    error_type: str
    error_message: str
    attempts: int

    def to_dict(self) -> dict[str, object]:
        return {
            **self.job.to_dict(),
            "error_type": self.error_type,
            "error_message": self.error_message,
            "attempts": self.attempts,
        }


def build_registry() -> dict[str, Handler]:
    """The complete type -> handler mapping.

    Built eagerly at import so that adding a job type without a handler is an
    ``ImportError`` at startup rather than an unclaimed message in a queue at 3am.
    """
    return {
        "ingest_document": _ingest_job.handle,
        "reindex_document": _reindex_job.handle,
        "reprocess_document": _reprocess_job.handle,
        "embed_chunks": _embed_job.handle,
        "purge_tombstoned": _purge_job.handle,
        "retention_sweep": _retention_job.handle,
        "feedback_analysis": _feedback_analysis_job.handle,
        "eval_sweep": _eval_sweep_job.handle,
    }


def unclaimed_types(registry: dict[str, Handler]) -> tuple[str, ...]:
    """Job types with no handler. Should always be empty; asserted at startup."""
    from worker.jobs import JobType

    declared = {
        value
        for name, value in vars(JobType).items()
        if not name.startswith("_") and isinstance(value, str)
    }
    return tuple(sorted(declared - set(registry)))


def decide(
    job: Job, error: BaseException, *, max_attempts: int = DEFAULT_MAX_ATTEMPTS
) -> RetryDecision:
    """Decide between retry and dead-letter for a failed job.

    ``NotImplementedError`` is dead-lettered immediately rather than retried. Retrying a
    handler that has not been written yet burns five delivery attempts to reach the same
    outcome, and each attempt is a queue message that had to be stored and replicated.
    """
    if isinstance(error, NotImplementedError):
        return RetryDecision(
            retry=False,
            dead_letter=True,
            next_attempt=job.attempt,
            reason="handler_not_implemented",
        )

    next_attempt = job.attempt + 1
    if next_attempt >= max_attempts:
        return RetryDecision(
            retry=False,
            dead_letter=True,
            next_attempt=next_attempt,
            reason="attempts_exhausted",
        )
    return RetryDecision(
        retry=True, dead_letter=False, next_attempt=next_attempt, reason="transient_failure"
    )


def consumer_retry_sleep(attempt: int, *, base: float = 1.0, cap: float = 60.0) -> float:
    """Exponential backoff, capped.

    The cap matters more than the curve: without it a long outage produces retry intervals
    that grow past the visibility timeout of most queues, so the message starts being
    redelivered by the broker as well as by the consumer.
    """
    if attempt < 0:
        raise ValueError("attempt must not be negative")
    return float(min(cap, base * (2.0**attempt)))


def process_one(
    job: Job,
    registry: dict[str, Handler],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> DeadLetter | None:
    """Run one job. Returns a :class:`DeadLetter` if the job failed terminally.

    Returning the dead letter rather than acknowledging it here keeps the broker interaction
    explicit at the call site: this function decides, the caller disposes.
    """
    handler = registry.get(job.type)
    if handler is None:
        # Unclaimed types are a deployment error, not a transient one. Dead-letter rather
        # than retry: retrying cannot make a handler appear.
        _logger.error(
            "no handler registered for job type",
            extra=log_extra(job_id=job.job_id, job_type=job.type, attempt=job.attempt),
        )
        return DeadLetter(
            job=job,
            error_type="UnclaimedJobType",
            error_message=f"no handler for job type {job.type!r}",
            attempts=job.attempt,
        )

    try:
        handler(job)
    except NotImplementedError as exc:
        _logger.info(
            "job handler not implemented",
            extra=log_extra(
                job_id=job.job_id,
                job_type=job.type,
                attempt=job.attempt,
                error_type=type(exc).__name__,
            ),
        )
        return DeadLetter(
            job=job,
            error_type=type(exc).__name__,
            error_message=str(exc),
            attempts=job.attempt,
        )
    except (AppError, Exception) as exc:  # noqa: BLE001 - the queue boundary sees everything
        decision = decide(job, exc, max_attempts=max_attempts)
        _logger.warning(
            "job failed",
            extra=log_extra(
                job_id=job.job_id,
                job_type=job.type,
                attempt=job.attempt,
                error_type=type(exc).__name__,
                will_retry=decision.retry,
                dead_letter=decision.dead_letter,
                # Message included because a job error is operational data about a
                # pipeline stage, not user content. Job payloads are validated elsewhere.
                error_message=str(exc),
            ),
        )
        if decision.retry:
            return None
        return DeadLetter(
            job=job,
            error_type=type(exc).__name__,
            error_message=str(exc),
            attempts=job.attempt,
        )
    return None
