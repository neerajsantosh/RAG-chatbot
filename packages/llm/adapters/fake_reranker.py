"""Deterministic offline reranker.

Scores by token overlap between query and passage, normalised by the longer of the two.
Crude next to a cross-encoder, but it is deterministic, needs no model, and -- unlike the
fake embeddings -- preserves the property reranking exists to exploit: a passage that
literally contains the query terms outranks one that merely looks similar in vector space.

Phase 5 tests rerank *plumbing* against this. Its scores are not evidence about rerank
quality, which requires the real cross-encoder and the golden dataset (FR-16, NFR-11).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Final

from llm.adapters.fake_embedder import tokenize

__all__ = ["FakeReranker"]

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)
"""Dropped before scoring. Without this, "what is the refund policy" matches every passage
containing "the", and the ranking becomes noise."""


def _content_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in _STOPWORDS]


_MIN_PREFIX_LENGTH: Final = 4
"""Only tokens at least this long are prefix-matched, so short words do not collide."""


def _overlap(query_tokens: Counter[str], passage_tokens: Counter[str]) -> int:
    """Count query tokens matched in the passage, allowing simple plural/prefix matches.

    "refund" must match "refunds" or the ranking is dominated by a tokenizer artefact
    rather than by relevance. This is not stemming -- it is enough to stop plurals and
    simple inflections from hiding a genuinely relevant passage.
    """
    matched = 0
    passage_vocabulary = set(passage_tokens)

    for token, count in query_tokens.items():
        hits = 0
        for candidate in passage_vocabulary:
            if _tokens_match(token, candidate):
                hits += 1
        matched += min(count, hits)

    return matched


def _tokens_match(query_token: str, passage_token: str) -> bool:
    if query_token == passage_token:
        return True
    shorter, longer = sorted((query_token, passage_token), key=len)
    if len(shorter) < _MIN_PREFIX_LENGTH:
        return False
    return longer.startswith(shorter)


class FakeReranker:
    """Token-overlap reranker with no model dependency."""

    __slots__ = ("_name", "_version")

    def __init__(self, *, name: str = "fake-rerank", model_version: str = "fake-rerank-v1") -> None:
        self._name = name
        self._version = model_version

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str:
        return self._version

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        query_counts = Counter(_content_tokens(query))
        if not query_counts:
            # No content words: every passage is equally (un)relevant. Returning 0.0 for
            # all is honest and lets the confidence gate refuse, which is the right
            # outcome for a query with nothing to match on.
            return [0.0] * len(passages)

        scores: list[float] = []
        for passage in passages:
            passage_vocabulary = _content_tokens(passage)
            if not passage_vocabulary:
                scores.append(0.0)
                continue

            overlap = _overlap(query_counts, Counter(passage_vocabulary))
            # Normalise by the longer token count, giving 0..1 with no length bias between
            # a two-word and a two-hundred-word passage beyond what is intended.
            denominator = max(len(query_counts), len(passage_vocabulary))
            scores.append(round(overlap / denominator, 6))

        return scores

    def top_n(self, query: str, passages: Sequence[str], n: int) -> list[tuple[int, float]]:
        """Highest score first. Ties broken by index, so the order is fully deterministic."""
        scored = list(enumerate(self.score(query, passages)))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored[: max(0, n)]
