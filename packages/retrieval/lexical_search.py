from __future__ import annotations

from typing import Sequence

from packages.retrieval.models import Hit, RankedList, RetrievedContext
from packages.storage.ports import VectorStore, LexicalStore


class LexicalSearch:
    """BM25/full-text search through the LexicalStore port, with the same ACL predicate."""

    def __init__(self, lexical_store: LexicalStore, user_groups: list[str] | None = None):
        self.lexical_store = lexical_store
        self.user_groups = user_groups or []

    def search(self, query: str, k: int = 6) -> RankedList:
        """Perform lexical search and apply ACL filtering."""
        # Perform lexical search
        raw_results = self.lexical_store.search(
            query=query,
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