"""Admin operations -- phase 1 stubs with authorisation already real.

The plan calls for "authz stubbed to deny non-operators", and that is exactly what happens:
:class:`~core.auth.principal.Principal.require_operator` is called in the handler body, so
the denial path is exercised in phase 1 rather than being deferred along with the
functionality it guards.

An endpoint that returns ``501`` to everyone would pass a smoke test and still ship a hole;
an endpoint that returns ``403`` to a non-operator and ``501`` to an operator proves both
halves of the contract today, with no privileged data to leak.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from api.deps import CurrentPrincipal
from api.routes._stubs import PlaceholderPayload, placeholder

__all__ = ["require_operator", "router"]

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def require_operator(principal: CurrentPrincipal) -> None:
    """Deny non-operators. Raises :class:`~core.errors.Forbidden`."""
    principal.require_operator()


@router.get("/status")
async def admin_status(principal: CurrentPrincipal) -> dict[str, object]:
    """Reachable by operators only. The one admin route that returns real data."""
    require_operator(principal)
    return {"implemented": False, "detail": "admin operations land in phase 4"}


@router.post("/reindex", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def reindex(principal: CurrentPrincipal) -> PlaceholderPayload:
    require_operator(principal)
    return placeholder("reindexing lands in phase 4")


@router.post("/acl-cache-refresh", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def refresh_acl_cache(principal: CurrentPrincipal) -> PlaceholderPayload:
    require_operator(principal)
    return placeholder("ACL cache refresh lands in phase 4")
