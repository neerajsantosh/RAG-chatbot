"""Cross-cutting middleware.

Ordering matters here and is the whole point of :mod:`api.app`. Added outermost-first, the
stack is:

1. :class:`~api.middleware.request_id.RequestIdMiddleware` -- a request id exists before
   anything can log, so even an immediate rejection is correlatable.
2. :class:`~api.middleware.timing.TimingMiddleware` -- duration and status are recorded for
   every request, including the rejected ones.
3. :class:`~api.middleware.auth.AuthMiddleware` -- the caller is authenticated and the
   immutable principal is bound to the request, or the request fails with 401.
4. :class:`~api.middleware.ratelimit.RateLimitMiddleware` -- the limit is keyed on that
   principal, which is only possible because auth ran first.

Auth before rate limit is deliberate: keying on IP alone would let one NAT'd office share a
single bucket and exhaust everyone else's budget.

Redaction is not in this list because it is not middleware. NFR-16 ("no document or user
content in logs") is enforced at the logging layer, so it holds even for a handler that
attaches content-bearing fields by mistake, and even on the error paths above. A guard that
depends on every developer remembering it eventually gets forgotten; a guard that cannot be
bypassed cannot.
"""

from __future__ import annotations

from api.middleware.auth import PUBLIC_PATHS, AuthMiddleware
from api.middleware.ratelimit import RateLimiter, RateLimitMiddleware
from api.middleware.request_id import RequestIdMiddleware
from api.middleware.timing import TimingMiddleware

__all__ = [
    "MIDDLEWARE_ORDER",
    "PUBLIC_PATHS",
    "AuthMiddleware",
    "RateLimitMiddleware",
    "RateLimiter",
    "RequestIdMiddleware",
    "TimingMiddleware",
]

#: The documented stack, outermost first. Asserted against the assembled app by
#: ``tests/unit/test_api_middleware_order.py`` so the order cannot drift silently.
MIDDLEWARE_ORDER = (
    RequestIdMiddleware,
    TimingMiddleware,
    AuthMiddleware,
    RateLimitMiddleware,
)
