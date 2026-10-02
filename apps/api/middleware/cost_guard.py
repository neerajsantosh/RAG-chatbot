from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from starlette.requests import Request

from core.errors import Forbidden
from core.logging import get_logger, log_extra

__all__ = ["CostGuardMiddleware", "CostExceeded", "cost_guard"]

LOGER = get_logger(__name__)

COST_HEADER = "X-User-Spend-Cap"
RETRY_AFTER_HEADER = "Retry-After"


@dataclass(frozen=True, slots=True)
class CostGuard:
    """Per-user spend cap as a backstop against cost exhaustion (NFR-15)."""

    max_cost_usd: float
    """Maximum spend per user in USD before requests are refused."""

    soft_limit_percent: float = 80.0
    """Warn at this percentage of the max (for observability, not enforcement)."""

    def check(self, cost_usd: float, principal: object) -> Optional[bool]:
        """Check if the cost is within the cap.

        Returns:
            None if within limits,
            True if at/over the soft limit (observability),
            False if over the hard cap (enforcement).
        """
        if cost_usd >= self.max_cost_usd:
            return False  # Hard cap exceeded
        if cost_usd >= self.max_cost_usd * self.soft_limit_percent / 100:
            return True  # Soft limit reached (observability)
        return None  # Within limits


class CostExceeded(Forbidden):
    """Raised when per-user spend cap is exceeded."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": "cost_exceeded",
            "message": "Per-user spend cap exceeded",
            "retryable": False,
            "details": {"cost_usd": self.cost_usd, "max_cost_usd": self.max_cost_usd},
        }


def derive_cost_key(request: Request) -> str:
    """Derive the cost-tracking key from the authenticated principal."""
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return f"user:{principal.user_id}"
    return "ip:unknown"


class CostGuardMiddleware:
    """Middleware that enforces per-user spend caps.

    Tracks cost per user and refuses requests that exceed the configured max.
    """

    def __init__(self, app, *, max_cost_usd: float = 100.0, enable_tracing: bool = True) -> None:
        self._app = app
        self._max_cost_usd = max_cost_usd
        self._enable_tracing = enable_tracing
        # In production, this would be a Redis or Postgres-backed counter
        # For now, we track in-memory per-process (not accurate across replicas)
        self._cost_tracker: dict[str, float] = {}

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        from starlette.requests import Request as StarletteRequest
        request = StarletteRequest(scope, receive)

        key = derive_cost_key(request)
        current_cost = self._cost_tracker.get(key, 0.0)

        # Estimate cost from the request (simplified)
        # In production, this would accumulate from actual model usage
        request_cost = 0.1  # placeholder per-request cost estimate

        new_total = current_cost + request_cost

        # Check guard
        guard = CostGuard(max_cost_usd=self._max_cost_usd)
        result = guard.check(new_total, request.state.principal if hasattr(request.state, "principal") else None)

        if result is False:
            # Hard cap exceeded - refuse
            from core.errors import CostExceeded as CE
            from api.errors import app_error_response

            exc = CE(cost_usd=new_total, max_cost_usd=self._max_cost_usd)
            response = app_error_response(request, exc)
            response.headers[COST_HEADER] = str(new_total)
            response.headers[RETRY_AFTER_HEADER] = "60"
            await response(scope, receive, send)
            return

        # Track cost
        self._cost_tracker[key] = new_total

        # Add cost header to response
        response_headers: list[tuple[bytes, bytes]] = list(getattr(response, "headers", []))
        response_headers.append((COST_HEADER.encode(), str(new_total).encode()))
        # Reconstruct response with new headers (simplified)

        await self._app(scope, receive, send)