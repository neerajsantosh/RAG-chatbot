"""Source documents -- phase 1 stubs.

Sources are the ingestion side of the product and are the first thing to be dangerous: an
unscoped source list leaks the existence of another tenant's documents even when no content
is returned. So every route here binds a principal even though it returns nothing, and the
admin surface in particular is denied outright to non-operators rather than stubbed open.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from api.deps import CurrentPrincipal
from api.routes._stubs import Collection, PlaceholderPayload, placeholder

__all__ = ["SourceResponse", "router"]

router = APIRouter(prefix="/v1/sources", tags=["sources"])


class SourceResponse(BaseModel):
    id: UUID
    name: str
    acl_tags: list[str] = Field(default_factory=list)
    visibility: str = "private"


@router.get("", response_model=Collection[SourceResponse])
async def list_sources(_: CurrentPrincipal) -> Collection[SourceResponse]:
    return Collection[SourceResponse]()


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_source(_: CurrentPrincipal) -> PlaceholderPayload:
    return placeholder("source ingestion lands in phase 2")


@router.get("/{source_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_source(source_id: UUID, _: CurrentPrincipal) -> PlaceholderPayload:
    return placeholder(f"source reads land in phase 2; requested id={source_id}")
