from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, List


@dataclass
class AuditRecord:
    """An append-only audit record for admin mutations."""
    record_id: str
    actor: str
    action: str  # e.g., "config_activate", "config_rollback", "user_create"
    target: str  # e.g., "config:v1", "user:alice"
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: __import__("datetime").datetime.utcnow().isoformat() + "Z")


class AuditRepository:
    """Append-only audit records for admin mutations."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        """Append an audit record. Never removes records."""
        self._records.append(record)

    def get_records(
        self,
        *,
        actor: str | None = None,
        action: str | None = None,
        target: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """Retrieve audit records with optional filtering."""
        filtered = self._records
        if actor is not None:
            filtered = [r for r in filtered if r.actor == actor]
        if action is not None:
            filtered = [r for r in filtered if r.action == action]
        if target is not None:
            filtered = [r for r in filtered if r.target == target]
        return filtered[-limit:]

    def get_all(self) -> list[AuditRecord]:
        """Return all audit records (for export/review)."""
        return self._records.copy()