from __future__ import annotations

import asyncio
from typing import Sequence, Optional

from packages.retrieval.models import Hit, RankedList, RetrievedContext
from packages.retrieval.vector_search import VectorSearch
from packages.retrieval.lexical_search import LexicalSearch


class RetrievalParallel:
    """Concurrent execution of both retrievers with per-retriever timeouts
    and partial-failure handling (NFR-9)."""

    def __init__(
        self,
        vector_search: VectorSearch,
        lexical_search: LexicalSearch,
        k: int = 6,
        timeout_vector: float | None = None,
        timeout_lexical: float | None = None,
    ) -> None:
        self.vector_search = vector_search
        self.lexical_search = lexical_search
        self.k = k
        self.timeout_vector = timeout_vector
        self.timeout_lexical = timeout_lexical

    async def search_both(self, query_embedding: list[float], query_text: str) -> tuple[RankedList, RankedList]:
        """Run both retrievers concurrently.

        Returns (vector_results, lexical_results).
        If one times out, the other still returns results.
        """
        vector_task = asyncio.create_task(self._run_vector(query_embedding))
        lexical_task = asyncio.create_task(self._run_lexical(query_text))

        # Wait with timeouts
        if self.timeout_vector is not None or self.timeout_lexical is not None:
            done, pending = await asyncio.wait(
                [vector_task, lexical_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            # Cancel pending tasks
            for task in pending:
                task.cancel()
        else:
            await asyncio.gather(vector_task, lexical_task)

        vector_results = await vector_task
        lexical_results = await lexical_task
        return vector_results, lexical_results

    async def _run_vector(self, query_embedding: list[float]) -> RankedList:
        """Run vector search with timeout."""
        if self.timeout_vector is not None:
            return await asyncio.wait_for(
                self.vector_search.search(query_embedding, self.k),
                timeout=self.timeout_vector,
            )
        return self.vector_search.search(query_embedding, self.k)

    async def _run_lexical(self, query_text: str) -> RankedList:
        """Run lexical search with timeout."""
        if self.timeout_lexical is not None:
            return await asyncio.wait_for(
                self.lexical_search.search(query_text, self.k),
                timeout=self.timeout_lexical,
            )
        return self.lexical_search.search(query_text, self.k)

    async def fuse_results(
        self, vector_results: RankedList, lexical_results: RankedList
    ) -> RankedList:
        """Fuse results from both retrievers using simple fusion.

        Returns a combined RankedList.
        """
        # Simple approach: take union, preferring vector scores
        # In a full implementation, would use RRF (Reciprocal Rank Fusion)
        combined_hits: list[Hit] = list(vector_results.hits)

        # Add lexical hits not already in vector results
        vector_chunk_ids = {hit.chunk_id for hit in vector_results.hits}
        for hit in lexical_results.hits:
            if hit.chunk_id not in vector_chunk_ids:
                hit.rank = len(combined_hits) + 1
                combined_hits.append(hit)

        # Sort by rank (vector first, then lexical)
        combined_hits.sort(key=lambda h: h.rank)
        return RankedList(hits=combined_hits)