"""Trace inspection -- phase 1 stub.

Traces carry the retrieval decisions for a single question, which makes them the most
content-adjacent read surface in the API. The route binds a principal and returns nothing.
Traces land in phase 5 with :class:`~core.telemetry.SpanRecorder` wired to storage.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel

from api.deps import CurrentPrincipal
from api.routes._stubs import Collection, PlaceholderPayload, placeholder

__all__ = ["TraceSummary", "router"]

router = APIRouter(prefix="/v1/traces", tags=["traces"])


class TraceSummary(BaseModel):
    trace_id: UUID
    conversation_id: UUID | None = None
    total_ms: float = 0.0


@router.get("", response_model=Collection[TraceSummary])
async def list_traces(_: CurrentPrincipal) -> Collection[TraceSummary]:
    return Collection[TraceSummary]()


@router.get("/{trace_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_trace(trace_id: UUID, _: CurrentPrincipal) -> PlaceholderPayload:
    return placeholder(f"trace reads land in phase 5; requested id={trace_id}")
