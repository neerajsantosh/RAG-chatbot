"""Chat with streaming -- phase 1 stub.

The response class, the media type and the event framing are real. The only events emitted
are ``start`` and ``done``, which is the FR-14 resolution in architecture Â§6.1: the client
learns the request was accepted and how it terminated, and nothing in between is invented.

No fabricated tokens are emitted. A stub that streamed placeholder text like
"Thinking..." would let the web client's SSE parser be written and appear to work against
output that phase 5 will never produce -- and a provisional answer that later retracts
itself is exactly the failure mode the stream design exists to avoid.

The event envelope is fixed now so the client's parser has a contract:

``{"event": "<name>", "data": {...}}``

one JSON object per ``text/event-stream`` data frame, with a blank line terminator. Named
``event:`` lines are not used, because the JSON payload already carries the name and having
two sources of truth for it is how a client ends up disagreeing with the server about which
event it is handling.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import CurrentPrincipal
from api.routes._stubs import placeholder
from core.ids import new_request_id

__all__ = [
    "MEDIA_TYPE_SSE",
    "ChatRequest",
    "ChatResponse",
    "SseEvent",
    "chat_stream",
    "format_sse",
    "router",
    "stub_event_stream",
]

MEDIA_TYPE_SSE = "text/event-stream"

router = APIRouter(prefix="/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """The request shape phase 5 implements. Fixed now so the web client's type is real."""

    conversation_id: str | None = Field(default=None, max_length=64)
    question: str = Field(min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    """Terminal state of a chat turn.

    Present so the non-streaming contract exists alongside the streaming one: a client that
    cannot handle SSE still has a typed shape to target.
    """

    request_id: str
    conversation_id: str | None = None
    answer: str = ""
    citations: list[str] = Field(default_factory=list)
    finished_reason: str = "phase_1_stub"


class SseEvent(BaseModel):
    event: str
    data: dict[str, Any] = Field(default_factory=dict)


def format_sse(event: SseEvent) -> str:
    """Render one event as a single ``text/event-stream`` frame."""
    payload = json.dumps(event.model_dump(), separators=(",", ":"), sort_keys=True)
    return f"data: {payload}\n\n"


async def stub_event_stream(request_id: str, conversation_id: str | None) -> AsyncIterator[str]:
    """Emit ``start`` then ``done`` and nothing else."""
    yield format_sse(SseEvent(event="start", data={"request_id": request_id}))
    yield format_sse(
        SseEvent(
            event="done",
            data={
                "request_id": request_id,
                "conversation_id": conversation_id,
                "finished_reason": "phase_1_stub",
            },
        )
    )


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def chat_stream(_: CurrentPrincipal) -> Any:
    """Placeholder for the non-streaming turn."""
    return placeholder("non-streaming chat lands in phase 5")


@router.post("/stream")
async def stream_chat(payload: ChatRequest, _: CurrentPrincipal) -> StreamingResponse:
    """SSE endpoint. Emits only the start and done events in phase 1.

    The ``question`` is validated but deliberately absent from every emitted event and from
    the returned headers: it is user content, and a stream is a durable, replayable record.
    """
    request_id = new_request_id()
    return StreamingResponse(
        stub_event_stream(request_id, payload.conversation_id),
        media_type=MEDIA_TYPE_SSE,
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Request-Id": request_id,
        },
    )
