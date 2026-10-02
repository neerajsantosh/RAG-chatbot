"""Rate limiting: the hook, without the algorithm.

Phase 1 installs this in the middleware chain but does **not** enforce a limit. That is a
deliberate staging decision, not an oversight:

- Enforcement needs a storage-backed counter (Redis or Postgres), and the plan places that
  in phase 4 with the rest of the rate-limit work. Shipping an in-process counter now would
  look like a working limit while being per-worker, which under multiple replicas quietly
  multiplies every configured limit by the replica count. A wrong limit is worse than a
  documented absent one.
- The seam is real rather than a comment: the key derivation, the decision type, the
  ``429`` response, the retry headers and the span attributes are all in place and tested.
  Phase 4 supplies a :class:`RateLimiter` and the enforcement switch flips.

The key is derived from the authenticated principal when there is one and from the client
address otherwise. Using the principal is the reason this middleware runs *after* auth:
keying on IP alone would let a single NAT'd office exhaust a shared bucket.

While unenforced the middleware still records the key and the remaining-budget annotation,
so phase 4 has real phase-1 traffic to calibrate against instead of a guess.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.errors import app_error_response
from core.errors import RateLimited
from core.logging import get_logger, log_extra
from core.telemetry import span

__all__ = [
    "HEADER_RETRY_AFTER",
    "Decision",
    "RateLimitMiddleware",
    "RateLimiter",
    "UnenforcedLimiter",
    "derive_key",
]

HEADER_RETRY_AFTER = "Retry-After"

_logger = get_logger(__name__)

# Paths that must not consume anyone's budget. Liveness and readiness probes fire
# continuously; if they counted against the limit, a healthy deploy could rate-limit its
# own health checks and take itself down.
_EXEMPT_PATHS = frozenset({"/healthz", "/readyz", "/version"})


@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome of one limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int = 0


class RateLimiter:
    """The interface phase 4 implements."""

    def check(self, key: str, cost: int = 1) -> Decision:
        raise NotImplementedError


class UnenforcedLimiter(RateLimiter):
    """Allows everything while reporting a nominal budget.

    ``remaining`` is reported as the full limit rather than a fabricated count of recent
    traffic, because inventing a number here would put a meaningless value in a response
    header that phase 4's consumers may already have started reading.
    """

    def __init__(self, limit: int = 0) -> None:
        self._limit = limit

    def check(self, key: str, cost: int = 1) -> Decision:
        return Decision(allowed=True, limit=self._limit, remaining=self._limit)


def derive_key(request: Request) -> str:
    """The bucket this request spends from.

    Prefers the authenticated principal. Falls back to the direct client address; note
    there is deliberately no ``X-Forwarded-For`` handling here, because trusting that
    header without an explicit trusted-proxy configuration would let a caller pick its own
    rate-limit key by forging a header.
    """
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return f"user:{principal.user_id}"
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies :class:`RateLimitMiddleware`'s decision and reports the budget."""

    def __init__(
        self,
        app: object,
        *,
        limiter: RateLimiter | None = None,
        enforce: bool = False,
        cost: int = 1,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limiter = limiter or UnenforcedLimiter()
        self._enforce = enforce
        self._cost = cost

    @property
    def enforcing(self) -> bool:
        return self._enforce

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        key = derive_key(request)
        exempt = request.url.path in _EXEMPT_PATHS

        decision = Decision(allowed=True, limit=0, remaining=0)
        if not exempt:
            decision = self._limiter.check(key, self._cost)

        with span(
            "ratelimit.check",
            rate_limit_key=key,
            rate_limit_allowed=decision.allowed,
            rate_limit_remaining=decision.remaining,
        ):
            if not decision.allowed:
                _logger.info(
                    "rate limit exceeded",
                    extra=log_extra(
                        rate_limit_key=key,
                        retry_after_seconds=decision.retry_after_seconds,
                        request_id=getattr(request.state, "request_id", ""),
                    ),
                )
                # Rendered here rather than raised: an exception from user middleware never
                # reaches the registered AppError handler, so raising would turn a 429 into
                # an opaque 500. See api.errors.app_error_response.
                denied = app_error_response(
                    request,
                    RateLimited(
                        "rate limit exceeded",
                        code="rate_limited",
                        details={
                            "limit": decision.limit,
                            "retry_after_seconds": decision.retry_after_seconds,
                        },
                    ),
                )
                denied.headers["Retry-After"] = str(
                    max(1, math.ceil(decision.retry_after_seconds))
                )
                denied.headers["X-RateLimit-Limit"] = str(decision.limit)
                denied.headers["X-RateLimit-Remaining"] = "0"
                return denied

            response = await call_next(request)

        if not exempt:
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, decision.remaining))
            if decision.retry_after_seconds:
                # Ceil so a fractional backoff never rounds *down* to "retry immediately".
                response.headers[HEADER_RETRY_AFTER] = str(
                    max(1, math.ceil(decision.retry_after_seconds))
                )
        return response
