"""Phase 1 route stubs.

Every route in this package is registered, typed and reachable, but returns an empty
collection or a placeholder payload. That is the phase-1 contract: the API *shape* is
fixed and reviewable now, and the behaviour lands in phases 2-5 behind those shapes.

Two rules the stubs obey, because breaking either would make the scaffolding actively
misleading:

**Empty is not error.** These return ``200`` with an empty list. A stub that raised
``501`` would make the smoke test green today and force every consumer to grow a
not-implemented branch before the real implementation exists.

**The principal is still required.** Every one of these routes depends on
:class:`~api.deps.current_principal`, so an unauthenticated request gets a 401
from the auth middleware before the handler is ever reached. A stub is not an excuse to
skip authorisation -- that is exactly how an empty endpoint becomes a real one without
anyone revisiting the guard.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

__all__ = ["Collection", "Page", "PlaceholderPayload", "placeholder"]

T = TypeVar("T")

ItemT = TypeVar("ItemT", bound=BaseModel)


class Collection(BaseModel, Generic[ItemT]):
    """The envelope every list endpoint returns.

    A bare JSON array cannot grow: adding pagination later means changing the response type
    and breaking every client. ``items`` plus ``total`` plus an explicit cursor can be
    introduced once, now, while there are no consumers to break.
    """

    items: list[ItemT] = Field(default_factory=list)
    total: int = 0
    next_cursor: str | None = None


class Page(Collection[ItemT], Generic[ItemT]):
    """A named page envelope, kept distinct from :class:`Collection` so callers can adopt
    cursored pagination later without another wire-format change."""


class PlaceholderPayload(BaseModel):
    """The body returned by endpoints whose shape is fixed but whose data is not.

    ``implemented`` is on the wire deliberately. A client that finds ``implemented: false``
    knows the emptiness is a phase boundary, not a statement that the user has no data --
    an empty ``items`` list is ambiguous between the two.
    """

    implemented: bool = False
    detail: str


def placeholder(detail: str) -> PlaceholderPayload:
    return PlaceholderPayload(implemented=False, detail=detail)
