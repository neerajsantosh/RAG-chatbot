from __future__ import annotations

from typing import Sequence

from packages.retrieval.models import Hit, RankedList, RetrievedContext
from packages.storage.ports import VectorStore, LexicalStore


class VectorSearch:
    """Dense search through the VectorStore port, with the ACL predicate inside the query."""

    def __init__(self, vector_store: VectorStore, user_groups: list[str] | None = None):
        self.vector_store = vector_store
        self.user_groups = user_groups or []

    def search(self, query_embedding: list[float], k: int = 6) -> RankedList:
        """Perform dense vector search and apply ACL filtering."""
        # Perform vector search
        raw_results = self.vector_store.query(
            query_embedding=query_embedding,
            k=k,
            user_groups=self.user_groups,
        )

        # Convert to RankedList
        hits: list[Hit] = []
        for i, (chunk_id, score, metadata) in enumerate(raw_results, 1):
            text = metadata.get("text", "")
            hits.append(
                Hit(
                    chunk_id=chunk_id,
                    score=score,
                    text=text,
                    metadata=metadata,
                    rank=i,
                )
            )

        return RankedList(hits=hits)