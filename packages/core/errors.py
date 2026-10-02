"""Typed error taxonomy.

Every error raised deliberately by this codebase derives from :class:`AppError` and
carries two things the rest of the system needs:

* ``code`` -- a stable machine-readable string. Logs, traces and API responses use
  the code; the human message is free to change.
* ``retryable`` -- whether retrying the same operation could plausibly succeed.

``retryable`` is what :mod:`core.retry` consults, so classifying an error correctly at
its definition site is the only place the decision is made. Getting it wrong here means
either giving up on recoverable failures or hammering a permanent one.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AppError",
    "ConfigurationError",
    "DependencyUnavailable",
    "EvaluationNotImplemented",
    "Forbidden",
    "NotFound",
    "ProviderAuthError",
    "ProviderError",
    "RateLimited",
    "TimeoutExceeded",
    "Unauthorized",
    "UnrecoverableProviderError",
    "ValidationFailed",
]


class AppError(Exception):
    """Base class for all deliberate errors raised by this codebase."""

    code: str = "app_error"
    retryable: bool = False
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        # Details are for operators, so they must never carry document or question
        # content. Callers are responsible for that; see core.logging.redaction.
        self.details: dict[str, Any] = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, retryable={self.retryable})"


class ConfigurationError(AppError):
    """Settings are missing or invalid. Startup fails; retrying cannot help."""

    code = "configuration_error"
    http_status = 500


class ValidationFailed(AppError):
    """Caller-supplied input did not pass validation."""

    code = "validation_failed"
    http_status = 422


class Unauthorized(AppError):
    """No usable credential was presented.

    Fail closed by design: an absent credential is never treated as an anonymous
    user who happens to be allowed.
    """

    code = "unauthorized"
    http_status = 401


class Forbidden(AppError):
    """Credential was valid but the principal lacks permission."""

    code = "forbidden"
    http_status = 403


class NotFound(AppError):
    code = "not_found"
    http_status = 404


class RateLimited(AppError):
    """A quota was exceeded. Retrying after the window may succeed."""

    code = "rate_limited"
    retryable = True
    http_status = 429

    def __init__(
        self, message: str, *, retry_after_seconds: float | None = None, **kwargs: Any
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class DependencyUnavailable(AppError):
    """A dependency we need is down.

    Raised when a retrieval store or similar is unreachable. Callers decide whether to
    degrade gracefully (NFR-9) or fail closed (NFR-10).
    """

    code = "dependency_unavailable"
    retryable = True
    http_status = 503

    def __init__(self, message: str, *, dependency: str | None = None, **kwargs: Any) -> None:
        details = dict(kwargs.pop("details", None) or {})
        if dependency:
            details["dependency"] = dependency
        super().__init__(message, details=details, **kwargs)
        self.dependency = dependency


class TimeoutExceeded(AppError):
    code = "timeout_exceeded"
    retryable = True
    http_status = 504


class ProviderError(AppError):
    """A model provider returned an error or an unusable response.

    Retryable by default: provider failures are usually transient.
    """

    code = "provider_error"
    retryable = True
    http_status = 502


class UnrecoverableProviderError(ProviderError):
    """Provider rejected the request in a way retrying will not fix."""

    code = "provider_unrecoverable"
    retryable = False
    http_status = 502


class ProviderAuthError(UnrecoverableProviderError):
    """Provider credentials are missing, expired, or rejected."""

    code = "provider_auth_error"


class EvaluationNotImplemented(AppError):
    """A metric was requested before the phase that implements it.

    Raised instead of returning a placeholder number. A silent zero in an evaluation
    report is indistinguishable from a real regression, which is worse than an error.
    """

    code = "evaluation_not_implemented"
    http_status = 501
