"""Injectable time source.

Two reasons this exists rather than calling :func:`time.time` inline:

* Freshness (NFR-7) and latency (NFR-1) are measured in seconds. Tests that sleep
  for real are slow and flaky; tests that patch ``time.time`` are order-dependent.
  Both call sites instead take a ``Clock``.
* The eval harness must be deterministic: "run the suite twice, get identical results"
  is a Phase 1 gate item, and wall-clock time is the usual reason that fails.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

__all__ = ["Clock", "FrozenClock", "SystemClock"]


@runtime_checkable
class Clock(Protocol):
    """Wall-clock and monotonic time."""

    def now(self) -> datetime:
        """Timezone-aware current UTC time."""
        ...

    def monotonic(self) -> float:
        """Seconds from an arbitrary origin. Never goes backwards."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block for ``seconds``."""
        ...


class SystemClock:
    """The real clock. The default everywhere outside tests."""

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class FrozenClock:
    """A clock that only moves when told to.

    Makes retention jobs, freshness checks and retry backoff testable without waiting
    and without patching.
    """

    __slots__ = ("_elapsed", "_sleeps", "_start")

    def __init__(self, start: datetime | None = None) -> None:
        self._start = start or datetime(2026, 1, 1, tzinfo=UTC)
        self._elapsed = 0.0
        self._sleeps: list[float] = []

    def now(self) -> datetime:
        return datetime.fromtimestamp(self._start.timestamp() + self._elapsed, tz=UTC)

    def monotonic(self) -> float:
        return self._elapsed

    def sleep(self, seconds: float) -> None:
        """Advance virtual time instead of blocking, and record the call."""
        self._sleeps.append(seconds)
        self._elapsed += max(0.0, seconds)

    def advance(self, seconds: float) -> None:
        """Move time forward without recording a sleep (e.g. simulating an edit)."""
        self._elapsed += max(0.0, seconds)

    @property
    def sleeps(self) -> list[float]:
        """Durations passed to :meth:`sleep`, in order. Useful for asserting backoff."""
        return list(self._sleeps)
