"""One retry decorator for every outbound call.

Every provider, database and object-store call goes through this, so timeouts,
bounded retries and backoff are configured in one place and inherited by every stage of
the pipeline rather than re-decided per call site.

Design notes:

* The retry decision is delegated to the error's ``retryable`` flag (see
  :mod:`core.errors`). Retrying a :class:`~core.errors.UnrecoverableProviderError` is
  not merely useless, it wastes the user's latency budget.
* Jitter is full jitter, not fixed backoff: without it, every worker that fails at the
  same instant retries at the same instant.
* ``clock`` and ``rng`` are injectable, which is what lets the test suite assert
  backoff behaviour without sleeping and without flaking.
"""

from __future__ import annotations

import functools
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar, cast

from core.clock import Clock, SystemClock
from core.errors import AppError

__all__ = ["RetryPolicy", "retry"]

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How many times to try, and how long to wait between attempts."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 8.0
    multiplier: float = 2.0
    jitter: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {self.max_attempts}")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must not be negative")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least 1")

    def delay_for(self, attempt: int, rng: random.Random) -> float:
        """Delay before ``attempt`` (1-based).

        Attempt 1 is immediate, so attempt 2 is the first that waits.
        """
        if attempt <= 1:
            return 0.0
        raw = self.base_delay_seconds * (self.multiplier ** (attempt - 2))
        capped = min(raw, self.max_delay_seconds)
        return rng.uniform(0.0, capped) if self.jitter else capped


def retry(
    policy: RetryPolicy | None = None,
    *,
    retry_on: Callable[[BaseException], bool] | None = None,
    clock: Clock | None = None,
    rng: random.Random | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a sync callable with bounded retries.

    Args:
        policy: Attempt count and backoff shape. Defaults to :data:`RetryPolicy`.
        retry_on: Override the decision function. Defaults to honouring the
            ``retryable`` flag on :class:`~core.errors.AppError`; a non-``AppError``
            exception is not retried, because an unexpected exception means a bug and
            bugs are not fixed by repetition.
        clock: Injectable for tests. Defaults to the system clock.
        rng: Injectable for tests, so jitter is reproducible.

    The re-raised error on exhaustion is the *last* error, with the attempt count
    recorded, so the caller sees why it actually failed rather than the first
    transient blip.
    """
    active_policy = policy or RetryPolicy()
    active_clock = clock or SystemClock()
    active_rng = rng or random.Random()
    should_retry = retry_on or _default_retry_on

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_error: BaseException | None = None

            for attempt in range(1, active_policy.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - decision delegated to should_retry
                    last_error = exc
                    if attempt >= active_policy.max_attempts or not should_retry(exc):
                        break
                    active_clock.sleep(active_policy.delay_for(attempt + 1, active_rng))

            assert last_error is not None  # loop ran at least once, so an error was captured
            if isinstance(last_error, AppError):
                last_error.details.setdefault("attempts", active_policy.max_attempts)
            raise last_error

        return wrapper

    return decorate


def async_retry(
    policy: RetryPolicy | None = None,
    *,
    retry_on: Callable[[BaseException], bool] | None = None,
    clock: Clock | None = None,
    rng: random.Random | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Async variant of :func:`retry`.

    Separate from the sync version rather than one implementation with a branch,
    because an ``await`` inside a sync retry loop is a bug that type checkers cannot
    catch.
    """
    import inspect

    active_policy = policy or RetryPolicy()
    active_clock = clock or SystemClock()
    active_rng = rng or random.Random()
    should_retry = retry_on or _default_retry_on

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            last_error: BaseException | None = None

            for attempt in range(1, active_policy.max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if inspect.isawaitable(result):
                        return await result
                    return result
                except Exception as exc:  # noqa: BLE001 - decision delegated to should_retry
                    last_error = exc
                    if attempt >= active_policy.max_attempts or not should_retry(exc):
                        break
                    active_clock.sleep(active_policy.delay_for(attempt + 1, active_rng))

            assert last_error is not None
            if isinstance(last_error, AppError):
                last_error.details.setdefault("attempts", active_policy.max_attempts)
            raise last_error

        return cast(Callable[P, R], wrapper)

    return decorate


def _default_retry_on(exc: BaseException) -> bool:
    return isinstance(exc, AppError) and exc.retryable
