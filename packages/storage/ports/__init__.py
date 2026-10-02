"""Repository ports.

The contracts that phase 2 onward implement. Three of them carry a ``principal``
parameter, and that is the single most important signature decision in the storage layer:
a repository that reads documents **cannot** be called without an authenticated caller.

Note the absence of an ``unfiltered`` variant. Any operation that must bypass access
control -- re-indexing, evaluation, corpus administration -- goes through the admin routes
with an operator role and an audit record, not through a second method on this interface.
A bypass that has to be looked for is much safer than one that is offered.

Protocol methods are declared, not implemented, here. Phase 1 ships no concrete
repositories because there are no tables yet; the ports exist so the API can be wired
against a contract and so that phase 2 has a fixed target.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from core.auth.principal import Principal

__all__ = [
    "ChunkRepository",
    "ConfigStore",
    "DocumentRepository",
    "DocumentStatus",
    "ObjectStore",
    "TraceRecord",
    "TraceStore",
    "VectorStore",
    "LexicalStore",
    "Visibility",
]


class Visibility:
    """How widely a document may be read."""

    ORG = "org"
    """Any bound principal may read it."""

    RESTRICTED = "restricted"
    """Requires a matching group in ``app.user_groups``."""


class DocumentStatus:
    """Lifecycle of a document through the indexing pipeline.

    A document is only retrievable in ``INDEXED``. The other states exist so that a
    half-ingested document can never be shown to a user, which is worse than stale content
    because it reads as authoritative.
    """

    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    DELETED = "deleted"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """A document's metadata. Carries no body text -- see :class:`ObjectStore`."""

    id: str
    source_id: str
    external_id: str
    title: str
    visibility: str = Visibility.ORG
    acl_tags: frozenset[str] = field(default_factory=frozenset)
    status: str = DocumentStatus.PENDING
    content_hash: str = ""
    chunker_version: str = ""
    embedding_model_version: str = ""
    canonical_uri: str = ""
    created_at: str = ""
    updated_at: str = ""
    indexed_at: str | None = None


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """One question's full retrieval and generation history (FR-33).

    Every field needed to reproduce an answer: what was asked, what was retrieved and with
    what scores, which prompt and configuration produced it, and what it cost. Deliberately
    separate from :class:`Message`, because a trace has a short retention window and a
    message may have a long one.
    """

    trace_id: str
    user_id: str
    question: str
    conversation_id: str | None = None
    message_id: str | None = None
    retrieved: tuple[dict[str, Any], ...] = ()
    admitted: tuple[str, ...] = ()
    refused: bool = False
    refusal_reason: str | None = None
    config_version: str = ""
    prompt_version: str = ""
    embedding_model: str = ""
    llm_model: str = ""
    stage_latency_ms: dict[str, float] = field(default_factory=dict)
    ttft_ms: int | None = None
    total_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@runtime_checkable
class DocumentRepository(Protocol):
    """Document metadata. Phase 2 implements this."""

    def get(self, principal: Principal, document_id: str) -> DocumentRecord | None:
        """Return the document if the principal may read it, else ``None``.

        ``None`` rather than a permission error: distinguishing "does not exist" from
        "not permitted" would leak the existence of documents the caller cannot read.
        """
        ...

    def list_for_source(
        self, principal: Principal, source_id: str, *, limit: int = 100
    ) -> Sequence[DocumentRecord]:
        """List documents in a source that the principal may read."""
        ...

    def upsert(self, principal: Principal, record: DocumentRecord) -> DocumentRecord:
        """Insert or update metadata. Operator-only in practice; audited at the route."""
        ...

    def set_status(self, principal: Principal, document_id: str, status: str) -> None:
        """Move a document through the indexing lifecycle."""
        ...

    def tombstone(self, principal: Principal, document_id: str) -> None:
        """Mark deleted. Retrieval must stop returning it immediately."""
        ...


@runtime_checkable
class ChunkRepository(Protocol):
    """Chunk text and embeddings. Phase 2 implements, phase 3 adds vector search."""

    def get_many(
        self, principal: Principal, chunk_ids: Sequence[str]
    ) -> Sequence[dict[str, Any]]:
        """Fetch chunks for the citation resolver, filtered by access.

        The read path re-checks access even though retrieval already filtered. The citation
        resolver runs later, from a different code path, and re-checking is cheap.
        """
        ...

    def search_dense(
        self,
        principal: Principal,
        embedding: Sequence[float],
        *,
        limit: int,
        over_fetch: int | None = None,
    ) -> Sequence[dict[str, Any]]:
        """Vector search with the ACL predicate inside the query (FR-8, FR-38).

        ``over_fetch`` fetches more than ``limit`` before ACL filtering so that a narrowly
        permissioned caller still receives a full result set.
        """
        ...

    def search_lexical(
        self, principal: Principal, query: str, *, limit: int, over_fetch: int | None = None
    ) -> Sequence[dict[str, Any]]:
        """Full-text search with the identical ACL predicate."""
        ...

    def write_active_set(self, principal: Principal, chunks: Sequence[dict[str, Any]]) -> None:
        """Atomically replace a document's active chunks.

        All-or-nothing by design: retrieval must never observe a document that is
        half-ingested (FR-5).
        """
        ...


@runtime_checkable
class TraceStore(Protocol):
    """Query history. Phase 4 implements; the interface exists so traces are never omitted
    by accident, since the write is on the request path (architecture driver D9)."""

    def append(self, record: TraceRecord) -> None:
        """Persist a completed query. Must not block the user response."""
        ...

    def get(self, trace_id: str) -> TraceRecord | None:
        ...

    def search(
        self,
        *,
        user_id: str | None = None,
        refused: bool | None = None,
        limit: int = 100,
    ) -> Sequence[TraceRecord]:
        ...


@runtime_checkable
class ConfigStore(Protocol):
    """Versioned prompts and retrieval configuration (FR-31, FR-35)."""

    def current(self) -> dict[str, Any]:
        """The active configuration, including its version."""
        ...

    def stage(self, config: dict[str, Any]) -> str:
        """Store a new version without activating it. Returns the version id."""
        ...

    def activate(self, version: str, *, actor: str) -> None:
        ...

    def rollback(self, *, actor: str) -> str:
        """Restore the previous active version. Returns the restored version id."""
        ...


@runtime_checkable
class ObjectStore(Protocol):
    """Raw and parsed document bytes. Phase 2 implements."""

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        """Write an immutable, versioned object. Returns its version id."""
        ...

    def get(self, key: str) -> bytes:
        """Read an object. Access control is the caller's responsibility -- the bucket must
        not become a way around the document ACL, which is why the corpus bucket holds only
        content the principal could already reach."""
        ...

    def delete(self, key: str) -> None:
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Dense vector search store. Phase 3 implements."""

    def query(
        self,
        query_embedding: Sequence[float],
        k: int,
        user_groups: list[str] | None = None,
    ) -> list[tuple[str, float, dict]]:
        """Perform ANN search with ACL filtering inside the query.

        Over-fetches so that narrowly permissioned callers still receive a full result set.
        """

    def upsert_vector(self, id: str, embedding: Sequence[float], metadata: dict) -> None:
        """Upsert a vector into the store."""

    def delete_vector(self, id: str) -> None:
        """Delete a vector from the store."""


@runtime_checkable
class LexicalStore(Protocol):
    """Full-text lexical search store. Phase 3 implements."""

    def search(
        self,
        query: str,
        k: int,
        user_groups: list[str] | None = None,
    ) -> list[tuple[str, float, dict]]:
        """Perform full-text search with ACL filtering inside the query.

        Uses the same ACL predicate as VectorStore so both retrievers cannot diverge.
        Over-fetches so that narrowly permissioned callers still receive a full result set.
        """

    def upsert_vector(self, id: str, embedding: Sequence[float], metadata: dict) -> None:
        """Not used by lexical store (stores text rank, not vectors)."""

    def delete_vector(self, id: str) -> None:
        """Not used by lexical store."""
