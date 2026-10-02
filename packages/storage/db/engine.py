"""Database engine and connection lifecycle.

Phase 1 treats the database as *optional*. That is a deliberate, temporary position, not a
design preference: ``/healthz`` must answer without a database so the local stack and CI are
useful, and ``/readyz`` must report honestly when the database is unreachable. Phase 3
flips ``DATABASE_REQUIRED`` to true and the distinction disappears.

The connection pool is created lazily and closed explicitly. Nothing here connects at
import time -- importing this module must never be able to hang a test collection or a
linter.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg import connect as _psycopg_connect
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from core.clock import Clock, SystemClock
from core.config.settings import Settings, get_settings
from core.errors import DependencyUnavailable
from core.logging import get_logger, log_extra

__all__ = ["DatabaseEngine", "get_engine", "reset_engine"]

_logger = get_logger(__name__)

Pool = ConnectionPool[Connection[Any]]

_PROBE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db-probe")
"""One worker for probes. A single thread is enough because probes are short, and bounding
the count keeps a database that is refusing connections from spawning an unbounded number
of threads in a process that is polling every few seconds."""


class DatabaseEngine:
    """Owns the connection pool and reports health.

    Not a repository and not a query helper on purpose: query construction belongs to
    repositories (phase 2), so that the ACL predicate is written in exactly one place.
    """

    __slots__ = ("_clock", "_pool", "_settings")

    def __init__(self, settings: Settings | None = None, *, clock: Clock | None = None) -> None:
        self._settings = settings or get_settings()
        self._clock = clock or SystemClock()
        self._pool: Pool | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def is_connected(self) -> bool:
        return self._pool is not None and not self._pool.closed

    def open(self) -> bool:
        """Open the pool if it is not already open. Returns whether it is usable.

        Never raises unless ``DATABASE_REQUIRED`` is set, in which case a startup that
        cannot reach its database should fail rather than serve traffic it cannot fulfil.
        A failure while the database is optional is logged and reported as not-connected,
        which is what lets ``/readyz`` answer 503 instead of dying.
        """
        if self.is_connected:
            return True

        pool = ConnectionPool(
            conninfo=self._settings.database_url.get_secret_value(),
            min_size=self._settings.database_pool_min_size,
            max_size=self._settings.database_pool_max_size,
            timeout=self._settings.database_connect_timeout_seconds,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=False,
        )

        try:
            # `wait` and `timeout` are separate parameters: `wait` is a bool, the timeout
            # is the seconds to spend waiting for it. Passing the timeout as `wait` blocks
            # forever, which is exactly the wrong behaviour for a health check.
            pool.open(
                wait=True, timeout=self._settings.database_connect_timeout_seconds
            )
        except Exception as exc:
            # Short close timeout: the default waits up to 30s for the pool's worker thread,
            # and a failing connect is exactly when that wait hurts most.
            pool.close(timeout=self._settings.database_connect_timeout_seconds)
            if self._settings.database_required:
                raise DependencyUnavailable(
                    "database connection failed",
                    dependency="postgres",
                    details={"reason": type(exc).__name__},
                ) from exc
            _logger.warning(
                "database unavailable, continuing without it",
                extra=log_extra(
                    dependency="postgres",
                    reason=type(exc).__name__,
                    database_required=self._settings.database_required,
                ),
            )
            self._pool = None
            return False

        self._pool = pool
        _logger.info(
            "database pool opened",
            extra=log_extra(
                pool_min_size=self._settings.database_pool_min_size,
                pool_max_size=self._settings.database_pool_max_size,
            ),
        )
        return True

    def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None and not pool.closed:
            pool.close()

    @contextmanager
    def connection(self) -> Iterator[Connection[Any]]:
        """Yield a pooled connection inside a transaction.

        Commits on success, rolls back on any exception. Callers must not commit
        themselves: a repository that can half-apply a write is worse than no repository.
        """
        if not self.open():
            raise DependencyUnavailable("database is not available", dependency="postgres")

        pool = self._pool
        assert pool is not None  # open() returned True, so the pool exists
        with pool.connection() as conn:
            try:
                yield conn
            except BaseException:
                conn.rollback()
                raise
            conn.commit()

    def check(self) -> bool:
        """Whether the database answers a trivial query. Never raises."""
        try:
            with self.connection() as conn:
                conn.execute("SELECT 1")
        except Exception:  # noqa: BLE001 - health checks report, they do not raise
            return False
        return True

    def probe(self, timeout_seconds: float = 2.0) -> bool:
        """Can the database be reached right now? Never raises, never uses the pool.

        Deliberately a separate, direct connection rather than the pool:

        * A readiness probe runs every few seconds. Going through the pool would open one
          on the first probe and hold it, which is state a health check should not create.
        * A pooled check pays the full pool-open timeout on every call while the database is
          down, which is exactly when probes are most frequent and least welcome.
        * The bound is a hard wall-clock deadline enforced here, not merely libpq's
          ``connect_timeout``. That parameter applies *per resolved address*, so a
          ``localhost`` DSN that yields ``::1`` and ``127.0.0.1`` takes up to twice the
          value -- four attempts on some machines, which turned a one-second probe into a
          four-second one. The endpoint's contract is that it answers promptly, so the
          deadline is enforced where that contract is written down.
        """
        future = _PROBE_EXECUTOR.submit(
            self._connect_and_probe,
            self._settings.database_url.get_secret_value(),
            # Give libpq slightly longer than our deadline so a hung socket is released
            # shortly after we stop waiting, rather than pinning a worker indefinitely.
            max(1, int(timeout_seconds) + 1),
        )
        try:
            return bool(future.result(timeout=timeout_seconds))
        except TimeoutError:
            future.cancel()
            _logger.warning(
                "database probe exceeded its deadline",
                extra=log_extra(dependency="postgres", timeout_seconds=timeout_seconds),
            )
            return False

    @staticmethod
    def _connect_and_probe(conninfo: str, connect_timeout: int) -> bool:
        try:
            with _psycopg_connect(
                conninfo=conninfo, connect_timeout=connect_timeout, autocommit=True
            ) as conn:
                conn.execute("SELECT 1")
        except Exception as exc:  # noqa: BLE001 - health checks report, they do not raise
            _logger.warning(
                "database probe failed",
                extra=log_extra(dependency="postgres", reason=type(exc).__name__),
            )
            return False
        return True

    def health(self) -> dict[str, Any]:
        """Health payload for ``/readyz``. Contains no credentials.

        ``required`` reports whether startup would fail without the database. It is
        informational: readiness does not consult it, because "the database is down" must
        produce 503 regardless of whether this deployment treats storage as mandatory.
        """
        reachable = self.probe(timeout_seconds=self._settings.database_probe_timeout_seconds)
        return {
            "dependency": "postgres",
            "reachable": reachable,
            "required": self._settings.database_required,
            "pool_open": self.is_connected,
        }

    def drop_pool(self) -> None:
        """Discard the pool without raising. Used by tests and by a failed reconnect."""
        pool, self._pool = self._pool, None
        if pool is not None and not pool.closed:
            pool.close()


_engine: DatabaseEngine | None = None


def get_engine(settings: Settings | None = None) -> DatabaseEngine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = DatabaseEngine(settings)
    return _engine


def reset_engine() -> None:
    """Close and discard the process-wide engine. Tests call this between cases."""
    global _engine
    if _engine is not None:
        _engine.close()
    _engine = None
