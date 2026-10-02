"""Conversation collection and CRUD -- phase 1 stubs.

`GET` returns an empty page. The mutations return ``501 Not Implemented`` rather than
pretending to succeed: a create that returned a fabricated id would let the web app build
against a fiction, and the bug would surface in phase 2 as "some conversations mysteriously
never persisted".

Read paths are stubbed as empty because empty is a truthful answer; write paths are stubbed
as unimplemented because a fabricated success is a lie. Both still require a principal, so
an unauthenticated caller gets 401 before reaching the handler.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from api.deps import CurrentPrincipal
from api.routes._stubs import Collection, PlaceholderPayload, placeholder

__all__ = ["ConversationResponse", "CreateConversationRequest", "router"]

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    """Write-side shape, fixed now so the phase-2 implementation has a contract to meet."""

    title: str | None = Field(default=None, max_length=200)


class ConversationResponse(BaseModel):
    id: UUID
    title: str | None = None
    created_at: str
    updated_at: str


@router.get("", response_model=Collection[ConversationResponse])
async def list_conversations(_: CurrentPrincipal) -> Collection[ConversationResponse]:
    """Always an empty page in phase 1: there is no conversation store yet."""
    return Collection[ConversationResponse]()


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_conversation(
    payload: CreateConversationRequest, _: CurrentPrincipal
) -> PlaceholderPayload:
    # The validated payload is described, not echoed: `title` is user content and NFR-16
    # keeps it out of the response body as well as the logs.
    return placeholder(
        f"conversation creation lands in phase 2; title length={len(payload.title or '')}"
    )


@router.get("/{conversation_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_conversation(conversation_id: UUID, _: CurrentPrincipal) -> PlaceholderPayload:
    return placeholder(f"conversation reads land in phase 2; requested id={conversation_id}")


@router.delete("/{conversation_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def delete_conversation(conversation_id: UUID, _: CurrentPrincipal) -> PlaceholderPayload:
    return placeholder(
        f"conversation deletion lands in phase 2; requested id={conversation_id}"
    )
