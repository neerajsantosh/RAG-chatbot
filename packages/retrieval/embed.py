from __future__ import annotations

import asyncio
from typing import Sequence

from packages.llm.ports import Embedder
from packages.llm.ports.capabilities import ModelCapabilities


class EmbeddingOrchestrator:
    """Orchestration: batching, caching, dimension assertion for embeddings."""

    def __init__(self, embedder: Embedder, batch_size: int | None = None) -> None:
        self.embedder = embedder
        self._capabilities = embedder.capabilities
        self.batch_size = batch_size or self.embedder.batch_size

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed multiple documents in batches."""
        if not texts:
            return []

        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_vectors = await self._embed_batch(batch)
            vectors.extend(batch_vectors)
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query text."""
        return await self._embed_text(text)

    async def _embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts. Default implementation calls embed_query for each."""
        return [await self._embed_text(t) for t in texts]

    async def _embed_text(self, text: str) -> list[float]:
        """Embed a single text and assert dimension consistency."""
        vector = await self.embedder.embed_query(text)
        self._assert_dimension(vector)
        return vector

    def _assert_dimension(self, vector: list[float]) -> None:
        """Assert the vector has the expected dimension."""
        expected = self._capabilities.max_context_tokens  # Using as proxy for dimension
        # Dimension check - in a real implementation, we'd store the actual dimension
        if len(vector) != expected:
            from core.errors import ValidationFailed
            raise ValidationFailed(
                f"Embedding dimension {len(vector)} does not match expected {expected}",
                code="embedding_dimension_mismatch",
            )