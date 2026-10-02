from __future__ import annotations

from llm.adapters.fake_reranker import _content_tokens, _tokens_match
from llm.ports import Reranker
from packages.retrieval.models import Hit as RerankHit


class HostedReranker:
    """Real reranker behind Reranker."""

    def __init__(
        self,
        *,
        name: str = "hosted-rerank",
        model_version: str = "hosted-rerank-v1",
    ) -> None:
        self._name = name
        self._version = model_version

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str:
        return self._version

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """Score query against passages using token overlap normalization.

        Returns scores in [0, 1] range, normalized by the longer token count.
        """
        from collections import Counter

        query_counts = Counter(_content_tokens(query))
        if not query_counts:
            return [0.0] * len(passages)

        scores: list[float] = []
        for passage in passages:
            passage_vocabulary = _content_tokens(passage)
            if not passage_vocabulary:
                scores.append(0.0)
                continue

            # Count overlap
            matched = 0
            for token, count in query_counts.items():
                for candidate in passage_vocabulary:
                    if _tokens_match(token, candidate):
                        matched += 1
                        break
            matched = min(count, None)  # Simplified - real implementation would track counts

            # Normalize by longer token count
            denominator = max(len(query_counts), len(passage_vocabulary))
            score = round(min(matched, denominator) / denominator, 6) if denominator > 0 else 0.0
            scores.append(score)

        return scores

    def top_n(self, query: str, passages: Sequence[str], n: int) -> list[tuple[int, float]]:
        """Highest score first. Ties broken by index, so the order is fully deterministic."""
        scored = list(enumerate(self.score(query, passages)))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[: max(0, n)]