"""Request duration and one span per request.

The summary log line carries method, path, status and duration -- and never the query
string or the request body. Both of those are content-bearing by construction, so this is
the first place in the request path where a handler's URL could otherwise reach a log.

Middleware order matters here. This sits outside the logging filter's scope on the error
path only in the sense that the filter is installed at the logging layer, not the handler
chain, so ordering does not change whether content is redacted.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.logging import get_logger, log_extra
from core.telemetry import span

__all__ = ["TimingMiddleware"]

_logger = get_logger(__name__)


class TimingMiddleware(BaseHTTPMiddleware):
    """Records one span per request and logs a summary line."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        request_id = getattr(request.state, "request_id", "")

        try:
            response = await call_next(request)
        except Exception:
            _logger.exception(
                "request failed",
                extra=log_extra(
                    method=request.method,
                    path=request.url.path,
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    request_id=request_id,
                ),
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        with span(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        ):
            response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"
            _logger.info(
                "request completed",
                extra=log_extra(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=round(duration_ms, 3),
                    request_id=request_id,
                ),
            )
        return response
