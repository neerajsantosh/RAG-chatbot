"""Answer feedback -- phase 1 stub.

The request model is real and validated, because feedback is worthless if it cannot be
validated: an unbound rating is uninterpretable data that later phases would have to clean
up from an opaque store.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from api.deps import CurrentPrincipal
from api.routes._stubs import PlaceholderPayload, placeholder

__all__ = ["FeedbackRequest", "router"]

router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    trace_id: UUID
    rating: int = Field(ge=1, le=5, description="1 is unhelpful, 5 is useful")
    comment: str | None = Field(default=None, max_length=4000)


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def submit_feedback(payload: FeedbackRequest, _: CurrentPrincipal) -> PlaceholderPayload:
    # The validated rating is described rather than echoed; a free-text comment is user
    # content and stays out of the response body.
    return placeholder(
        f"feedback submission lands in phase 5; accepted rating={payload.rating} "
        f"has_comment={payload.comment is not None}"
    )
