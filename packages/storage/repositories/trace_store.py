from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, List

from packages.storage.ports import TraceRecord, TraceStore as TraceStoreProtocol
from packages.storage.repositories.audit_repository import AuditRecord, AuditRepository


@dataclass
class _TraceRecord:
    """Internal trace record storage model."""
    trace_id: str
    user_id: str
    question: str
    conversation_id: str | None = None
    session_id: str | None = None
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    llm_response: str | None = None
    cost_usd: float = 0.0
    ttft_ms: int | None = None
    total_ms: int = 0
    status: str = "completed"  # completed, refused, error
    refusal_reason: str | None = None


class TraceStore(TraceStoreProtocol):
    """Append trace records; buffered so analytics never block a user response."""

    def __init__(self) -> None:
        self._records: List[_TraceRecord] = []
        self._audit = AuditRepository()  # Internal audit trail

    def append(self, record: _TraceRecord) -> None:
        """Persist a completed query. Must not block the user response."""
        if not record.trace_id:
            record.trace_id = str(uuid.uuid4())
        self._records.append(record)
        # Also append to audit trail
        audit = AuditRecord(
            record_id=record.trace_id,
            actor=record.user_id,
            action="query_completed",
            target=f"trace:{record.trace_id}",
            details={
                "question": record.question,
                "cost_usd": record.cost_usd,
                "status": record.status,
            },
        )
        self._audit.append(audit)

    def get(self, trace_id: str) -> _TraceRecord | None:
        """Retrieve a trace by ID."""
        for record in self._records:
            if record.trace_id == trace_id:
                return record
        return None

    def search(
        self,
        *,
        user_id: str | None = None,
        refused: bool | None = None,
        limit: int = 100,
    ) -> List[_TraceRecord]:
        """Search traces with optional filtering."""
        filtered = self._records
        if user_id is not None:
            filtered = [r for r in filtered if r.user_id == user_id]
        if refused is not None:
            filtered = [r for r in filtered if (r.status == "refused") == refused]
        return filtered[:limit]

    def get_audit(self) -> AuditRepository:
        """Return the internal audit repository for review/export."""
        return self._audit