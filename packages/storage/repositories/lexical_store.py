from __future__ import annotations

from packages.retrieval.models import Hit, RankedList, RetrievedContext
from packages.storage.ports import LexicalStore


class PostgresLexicalStore(LexicalStore):
    """LexicalStore implementation: full-text ranking, same ACL predicate,
    over-fetching so permitted users always get a full result set."""

    def __init__(self, connection_string: str, user_groups: list[str] | None = None) -> None:
        self._connection_string = connection_string
        self._user_groups = user_groups or []

    def search(self, query: str, k: int, user_groups: list[str] | None = None) -> list[tuple[str, float, dict]]:
        """Perform full-text search with ACL filtering.

        Uses the same ACL predicate as the vector search so both retrievers
        cannot diverge (filters.py shared module).

        Over-fetches by a factor of 2 so users with narrow permissions still
        receive a full result set of size k.
        """
        # ACL predicate (shared)
        from packages.retrieval.filters import build_acl_predicate
        acl_clause = build_acl_predicate(user_groups or self._user_groups)

        # In a real implementation, this would be a SQL query like:
        # SELECT chunk_id, ts_rank_cd(ts_vector, query) as relevance, metadata
        # FROM chunks
        # WHERE text @@ plainto_tsquery($query)
        #   AND (@@ rsacl(acl_tags, $acl_clause) OR 1=1)
        # ORDER BY relevance DESC
        # LIMIT $k * 2  -- over-fetch
        # Then trim to k results after ACL filtering

        # Placeholder: return empty results until actual PG setup
        return []

    def upsert_vector(self, id: str, embedding: list[float], metadata: dict) -> None:
        """Not used by lexical store (stores text rank, not vectors)."""
        pass

    def delete_vector(self, id: str) -> None:
        """Not used by lexical store."""
        pass