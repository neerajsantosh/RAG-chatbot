"""Request correlation.

A request id is generated (or accepted, if it arrives well-formed) so that a single user
report can be traced to every log line and span the request produced.

The inbound header is validated rather than trusted. This value is echoed in the response
and written to every log line for the request, so an unvalidated echo is a log-injection
vector: a caller could otherwise smuggle newlines and forge log entries. Anything that does
not match the expected format is discarded and a fresh id is minted.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.ids import HEADER_REQUEST_ID, new_request_id

__all__ = ["MAX_REQUEST_ID_LENGTH", "RequestIdMiddleware", "is_safe_request_id"]

MAX_REQUEST_ID_LENGTH = 64


def is_safe_request_id(value: str) -> bool:
    """Whether an inbound request id may be reused verbatim."""
    if not value or len(value) > MAX_REQUEST_ID_LENGTH:
        return False
    return all(char.isalnum() or char in "-_" for char in value)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns a request id to ``request.state`` and echoes it on the response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inbound = request.headers.get(HEADER_REQUEST_ID, "")
        request_id = inbound if is_safe_request_id(inbound) else new_request_id()
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[HEADER_REQUEST_ID] = request_id
        return response
