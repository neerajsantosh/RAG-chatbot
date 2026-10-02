from __future__ import annotations

from packages.ingest.models import Chunk


class ChunkRepository:
    """Write chunk sets, flip the active set atomically, tombstone old rows."""

    async def write_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        """Write chunks for a document, replacing any existing ones."""
        raise NotImplementedError

    def tombstone_chunks(self, document_id: str) -> None:
        """Tombstone all chunks for a deleted document."""
        raise NotImplementedError