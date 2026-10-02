from __future__ import annotations

from typing import Sequence

from packages.retrieval.models import Chunk, Hit
from packages.storage.ports import ChunkRepository


class IndexWriter:
    """Persists embeddings for new and changed chunks; drives the phase-2 indexer
    with vectors attached."""

    def __init__(self, chunk_repository: ChunkRepository, vector_store: object) -> None:
        self.chunk_repository = chunk_repository
        self.vector_store = vector_store

    async def write_embeddings(self, chunks: Sequence[Chunk], vectors: Sequence[list[float]]) -> None:
        """Write embeddings for a batch of chunks.

        Associates each chunk's embedding with the vector store,
        ensuring idempotent updates.
        """
        if len(chunks) != len(vectors):
            raise ValueError(
                f"Mismatch: {len(chunks)} chunks but {len(vectors)} vectors"
            )

        for chunk, vector in zip(chunks, vectors):
            # Write vector to vector store with chunk hash as ID
            await self.vector_store.upsert_vector(
                id=chunk.hash,
                embedding=vector,
                metadata={
                    "chunk_text": chunk.text,
                    "source_file": chunk.source_file if hasattr(chunk, 'source_file') else "",
                    "acl_tags": chunk.acl_tags if hasattr(chunk, 'acl_tags') else [],
                },
            )

            # Update chunk record in repository to mark embedding as written
            await self.chunk_repository.mark_embedding_written(chunk.hash)

    async def update_changed_chunks(
        self, old_chunks: Sequence[Chunk], new_chunks: Sequence[Chunk], new_vectors: Sequence[list[float]]
    ) -> None:
        """Update embeddings for changed chunks only.

        Tombstones old vectors and writes new ones.
        """
        # Tombstone old chunk embeddings
        for chunk in old_chunks:
            await self.vector_store.delete_vector(id=chunk.hash)

        # Write new/changed embeddings
        await self.write_embeddings(new_chunks, new_vectors)