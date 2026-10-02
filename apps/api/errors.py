"""Exception handlers.

One handler for the whole :class:`~core.errors.AppError` taxonomy, so every deliberate
failure leaves the process the same way: a stable ``code`` in the response, a mapped HTTP
status, and a log line that identifies the request without quoting the input that caused
it.

The response body carries no ``details`` from the exception. Those are for operators and go
to the log. An error message that echoes a rejected value is a small, self-contained
information leak, and there is no compensating benefit to putting it in the response.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.errors import AppError
from core.logging import get_logger, log_extra

__all__ = [
    "app_error_response",
    "error_response",
    "install_exception_handlers",
]

_logger = get_logger(__name__)


def error_response(
    code: str, message: str, status_code: int, request_id: str = ""
) -> JSONResponse:
    body: dict[str, object] = {"error": {"code": code, "message": message}}
    headers = {"X-Request-Id": request_id} if request_id else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def app_error_response(request: Request, exc: AppError) -> JSONResponse:
    """Log and render an :class:`AppError` in the standard envelope.

    Split out of the handler registration because Starlette's ``ExceptionMiddleware`` only
    wraps the router. An :class:`AppError` raised inside *user middleware* -- which is
    exactly what the auth and rate-limit middleware do -- therefore never reaches a handler
    registered with ``@app.exception_handler``, and would surface as an opaque 500. Calling
    this from the middleware itself keeps one response shape for every failure, whether it
    came from a dependency, a handler, or a middleware.

    The log level is chosen by consequence, not by how the error was raised.
    """
    request_id = _request_id(request)
    level = _logger.error if exc.http_status >= 500 else _logger.info
    level(
        "request rejected",
        extra=log_extra(
            error_code=exc.code,
            status_code=exc.http_status,
            path=request.url.path,
            method=request.method,
            request_id=request_id,
            error_type=type(exc).__name__,
        ),
    )
    return error_response(exc.code, exc.message, exc.http_status, request_id)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return app_error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI's own error body echoes the submitted value, which for this API could be
        # a question. Replaced with a fixed message; the count of problems is the only
        # useful part and it is not content-bearing.
        problem_count = len(exc.errors())
        _logger.info(
            "request validation failed",
            extra=log_extra(
                problem_count=problem_count,
                path=request.url.path,
                request_id=_request_id(request),
            ),
        )
        return error_response(
            "validation_failed",
            f"request body failed validation ({problem_count} problem(s))",
            422,
            _request_id(request),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return error_response(
            "http_error", str(exc.detail), exc.status_code, _request_id(request)
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # The one place an unexpected exception is logged with its type and no content.
        # The traceback goes to the log for operators; the caller gets a code it can quote.
        _logger.exception(
            "unhandled exception",
            extra=log_extra(
                error_type=type(exc).__name__,
                path=request.url.path,
                method=request.method,
                request_id=_request_id(request),
            ),
        )
        return error_response(
            "internal_error", "an unexpected error occurred", 500, _request_id(request)
        )
