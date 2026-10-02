from __future__ import annotations

from packages.ingest.models import Chunk, ParsedDocument, SourceRef


class DocumentRepository:
    """Upsert documents; status transitions; tombstone."""

    async def upsert(self, document: ParsedDocument) -> str:
        """Upsert a document and return its document_id."""
        raise NotImplementedError

    def tombstone(self, document_id: str) -> None:
        """Mark a document as deleted (tombstone)."""
        raise NotImplementedError


class ChunkRepository:
    """Write chunk sets, flip the active set atomically, tombstone old rows."""

    async def write_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        """Write chunks for a document, replacing any existing ones."""
        raise NotImplementedError

    def tombstone_chunks(self, document_id: str) -> None:
        """Tombstone all chunks for a deleted document."""
        raise NotImplementedError