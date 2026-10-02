"""Ingestion worker.

Phase 1 runs a queue loop with nothing to consume. That sounds like an empty file, but the
part worth building now is the *shutdown behaviour*, because it is the part that is normally
omitted and then causes the bug.

The behaviour that matters:

* **A poll loop must notice cancellation promptly.** The loop sleeps between polls, and that
  sleep is interruptible. A plain ``time.sleep`` in the loop body means a container stop
  takes the full poll interval to take effect, and under load the orchestrator's grace
  period expires and kills the process mid-job.
* **In-flight work finishes before shutdown.** Cancellation is checked between jobs, not
  inside one, so a job that has started is allowed to complete.
* **A failing job does not kill the worker.** The handler raises, the error is recorded, and
  the loop continues. A worker that exits on the first bad message turns one poisoned
  message into a full outage.

Phase 2 fills in :class:`JobHandler`; the loop, the cancellation and the error accounting
do not change.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from core.clock import Clock, SystemClock
from core.config.settings import Settings, get_settings
from core.errors import AppError, ConfigurationError
from core.logging import configure_logging, get_logger, log_extra
from core.telemetry import span
from worker.consumer import build_registry, process_one, unclaimed_types
from worker.jobs import Job

__all__ = ["Worker", "WorkerStats", "main"]

_logger = get_logger(__name__)

JobHandler = Callable[[Job], Awaitable[None]]
"""Phase 2 replaces the placeholder handler with a real one; the loop does not change."""


@dataclass
class WorkerStats:
    """Counters worth having on the wall during an incident."""

    polls: int = 0
    jobs_handled: int = 0
    jobs_failed: int = 0
    shutdowns: int = 0

    def to_log_fields(self) -> dict[str, int]:
        return {
            "polls": self.polls,
            "jobs_handled": self.jobs_handled,
            "jobs_failed": self.jobs_failed,
        }


@dataclass
class Worker:
    """A cancellable poll loop over a job source."""

    handler: Callable[[Job], Awaitable[None]]
    poll_interval_seconds: float = 1.0
    clock: Clock = field(default_factory=SystemClock)
    stats: WorkerStats = field(default_factory=WorkerStats)
    job_source: Callable[[], Awaitable[list[Job]]] | None = None
    """Supplied by the queue client in phase 2. ``None`` means "nothing to poll", which
    is the honest Phase 1 state: there is no queue yet, so the worker idles rather than
    pretending to be connected to one."""

    async def run(self, *, stop: asyncio.Event | None = None) -> None:
        """Poll until cancelled. Returns cleanly when ``stop`` is set."""
        shutdown = stop or asyncio.Event()
        _logger.info(
            "worker started",
            extra=log_extra(poll_interval_seconds=self.poll_interval_seconds),
        )

        try:
            while not shutdown.is_set():
                self.stats.polls += 1
                jobs = await self._fetch()
                for job in jobs:
                    if shutdown.is_set():
                        # Checked between jobs, not inside one: work that has started finishes.
                        _logger.info("shutdown requested; finishing after current job")
                        break
                    await self._run_one(job)

                # Interruptible, so a stop request is honoured promptly instead of at the end
                # of the next poll interval.
                await self._sleep_interruptibly(self.poll_interval_seconds, shutdown)
        except _ShutdownError:
            # The sleep noticed the stop. Caught here rather than in the caller so that
            # `run()` honours its own contract of returning cleanly, and a caller does not
            # have to know that this internal signal exists.
            pass

        self.stats.shutdowns += 1
        _logger.info("worker stopped", extra=log_extra(**self.stats.to_log_fields()))

    async def _fetch(self) -> list[Job]:
        if self.job_source is None:
            return []
        try:
            return await self.job_source()
        except Exception as exc:  # noqa: BLE001 - a queue client can raise anything; the loop survives
            # A queue that is briefly unreachable must not stop the loop.
            _logger.warning(
                "job source unavailable", extra=log_extra(error_type=type(exc).__name__)
            )
            return []

    async def _run_one(self, job: Job) -> None:
        job_id = job.job_id
        with span("worker.job", job_id=job_id, job_type=job.type):
            try:
                await self.handler(job)
            except AppError as exc:
                # Expected operational failure: recorded, not retried here. The queue's
                # own visibility timeout decides whether it comes back.
                self.stats.jobs_failed += 1
                _logger.warning(
                    "job failed",
                    extra=log_extra(
                        job_id=job_id, error_code=exc.code, error_type=type(exc).__name__
                    ),
                )
            except Exception as exc:
                self.stats.jobs_failed += 1
                _logger.exception(
                    "job raised an unexpected error",
                    extra=log_extra(job_id=job_id, error_type=type(exc).__name__),
                )
            else:
                self.stats.jobs_handled += 1
                _logger.info("job handled", extra=log_extra(job_id=job_id))

    async def _sleep_interruptibly(self, seconds: float, stop: asyncio.Event) -> None:
        """Sleep, but wake immediately when shutdown is requested."""
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            return
        raise _ShutdownError


class _ShutdownError(Exception):
    """Internal signal that a stop was requested while sleeping."""


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
    def request_stop(signal_name: str) -> None:
        _logger.info("shutdown signal received", extra=log_extra(signal=signal_name))
        stop.set()

    def on_signal(signal_name: str) -> Callable[[], None]:
        def handler() -> None:
            request_stop(signal_name)

        return handler

    for signal_name in ("SIGINT", "SIGTERM"):
        signal_number = getattr(signal, signal_name, None)
        if signal_number is None:
            continue
        try:
            loop.add_signal_handler(
                signal_number, on_signal(signal_name.upper())
            )
        except NotImplementedError:
            # Windows has no loop-level signal handlers; KeyboardInterrupt is handled
            # instead in main().
            _logger.debug(
                "loop signal handlers unavailable on this platform",
                extra=log_extra(signal=signal_name),
            )


async def _run(settings: Settings) -> None:
    # The real registry, so the dispatch path exercised in phase 1 is the same one phase 2
    # uses. Every handler raises NotImplementedError today; the retry, dead-letter and
    # accounting behaviour around them is already live.
    registry = build_registry()

    missing = unclaimed_types(registry)
    if missing:
        # A declared job type with no handler would sit in the queue forever. Refuse to
        # start rather than accept messages nothing will claim.
        raise ConfigurationError(
            f"no handler registered for job types: {', '.join(missing)}",
            code="job_types_unclaimed",
        )

    async def dispatch(job: Job) -> None:
        dead_letter = process_one(job, registry, max_attempts=settings.worker_max_attempts)
        if dead_letter is not None:
            # Phase 1 has no broker to move this to, so the record is logged. The
            # disposition -- retry or dead-letter -- is already decided by process_one and
            # is not this function's business.
            _logger.error(
                "job dead-lettered",
                extra=log_extra(
                    job_id=dead_letter.job.job_id,
                    job_type=dead_letter.job.type,
                    attempts=dead_letter.attempts,
                    error_type=dead_letter.error_type,
                ),
            )

    worker = Worker(
        handler=dispatch,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
        clock=SystemClock(),
    )

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    _install_signal_handlers(loop, stop)

    await worker.run(stop=stop)


def main() -> int:
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=str(settings.log_format))
    _logger.info(
        "worker configured",
        extra=log_extra(
            environment=str(settings.environment),
            embedding_model=settings.embedding_model,
            embedding_model_version=settings.embedding_model_version,
        ),
    )
    try:
        asyncio.run(_run(settings))
    except KeyboardInterrupt:
        _logger.info("worker interrupted")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
