"""Deterministic retrieval metrics.

No model is involved. That is the point: these numbers are reproducible, free, and fast
enough to run on every commit, so they are the primary signal behind the NFR-12 release
gate. Judged metrics (phase 5) corroborate; they cannot replace them.

Definitions used here:

* ``recall@k`` -- the fraction of gold supporting ids present in the top k results. The
  primary metric, because a single missed supporting passage usually means a wrong answer.
* ``hit_rate@k`` -- the fraction of questions with at least one gold id in the top k.
  Reported alongside recall so a perfect-recall-one-passage corpus does not flatter itself.
* ``mrr@k`` -- mean reciprocal rank of the first gold id. Sensitive to *rank*, which
  recall is not, and rank drives the context budget.
* ``ndcg@k`` -- graded ranking quality over binary relevance.
* ``oracle_union`` -- recall over the union of the two retrievers. Not a shipping metric;
  it is the ceiling hybrid fusion could reach, and it is what justifies the extra
  complexity (or shows it was not worth it).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "DEFAULT_KS",
    "RetrievalMetrics",
    "aggregate",
    "ndcg_at_k",
    "oracle_union_recall",
    "per_question_recall",
    "score_question",
]

DEFAULT_KS: tuple[int, ...] = (1, 3, 5, 10)
"""Cutoffs reported by default. 5 is the headline figure referenced by G5 and NFR-12."""


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    """Aggregate retrieval quality for one run."""

    question_count: int = 0
    recall_at_k: dict[int, float] = field(default_factory=dict)
    hit_rate_at_k: dict[int, float] = field(default_factory=dict)
    mrr_at_k: dict[int, float] = field(default_factory=dict)
    ndcg_at_k: dict[int, float] = field(default_factory=dict)
    by_stratum: dict[str, dict[int, float]] = field(default_factory=dict)
    oracle_union: float | None = None
    """Recall over the union of both retrievers, when a second retriever was run.

    Not a shipping metric -- it is not a retrieval system -- but it bounds what fusion
    could achieve and therefore whether a second retriever is worth its complexity.
    ``None`` rather than ``0.0`` when no second retriever ran, so an absent measurement is
    never read as a ceiling of zero.
    """

    def headline(self, k: int = 5) -> float:
        """The number the release gate reads."""
        return self.recall_at_k.get(k, 0.0)

    def to_dict(self) -> dict[str, object]:
        return {
            "question_count": self.question_count,
            "recall_at_k": {str(k): round(v, 6) for k, v in sorted(self.recall_at_k.items())},
            "hit_rate_at_k": {str(k): round(v, 6) for k, v in sorted(self.hit_rate_at_k.items())},
            "mrr_at_k": {str(k): round(v, 6) for k, v in sorted(self.mrr_at_k.items())},
            "ndcg_at_k": {str(k): round(v, 6) for k, v in sorted(self.ndcg_at_k.items())},
            "oracle_union": (
                None if self.oracle_union is None else round(self.oracle_union, 6)
            ),
            "by_stratum": {
                stratum: {str(k): round(v, 6) for k, v in sorted(values.items())}
                for stratum, values in sorted(self.by_stratum.items())
            },
        }


def _top_k(retrieved: Sequence[str], k: int) -> list[str]:
    return list(retrieved[:k])


def per_question_recall(retrieved: Sequence[str], gold: frozenset[str], k: int) -> float:
    """Fraction of gold ids found in the top k. 0.0 when gold is empty."""
    if not gold:
        return 0.0
    found = set(_top_k(retrieved, k)) & gold
    return len(found) / len(gold)


def score_question(
    retrieved: Sequence[str], gold: frozenset[str], *, ks: Sequence[int] = DEFAULT_KS
) -> dict[str, float]:
    """All metrics for one question, keyed by metric name."""
    scores: dict[str, float] = {}
    for k in ks:
        window = _top_k(retrieved, k)
        scores[f"recall@{k}"] = per_question_recall(retrieved, gold, k)
        scores[f"hit_rate@{k}"] = 1.0 if set(window) & gold else 0.0
        scores[f"mrr@{k}"] = _reciprocal_rank(window, gold)
        scores[f"ndcg@{k}"] = ndcg_at_k(window, gold, k)
    return scores


def _reciprocal_rank(ranked: Sequence[str], gold: frozenset[str]) -> float:
    for position, item in enumerate(ranked, start=1):
        if item in gold:
            return 1.0 / position
    return 0.0


def ndcg_at_k(ranked: Sequence[str], gold: frozenset[str], k: int) -> float:
    """Normalised discounted cumulative gain with binary relevance."""
    if not gold:
        return 0.0

    gains = [1.0 if item in gold else 0.0 for item in ranked[:k]]
    dcg = sum(gain / math.log2(position + 1) for position, gain in enumerate(gains, start=1))

    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_hits + 1))

    return round(dcg / idcg, 6) if idcg else 0.0


def oracle_union_recall(
    per_retriever: Sequence[Sequence[str]], gold: frozenset[str], k: int
) -> float:
    """Recall over the union of several ranked lists.

    The ceiling hybrid fusion could reach. Not shippable as a metric -- it is not a
    retrieval system -- but it answers the only question that matters when deciding whether
    to add a second retriever: how much is left on the table.
    """
    if not gold:
        return 0.0
    union = {item for ranked in per_retriever for item in _top_k(ranked, k)}
    return len(union & gold) / len(gold)


def aggregate(
    per_question: Sequence[tuple[str, dict[str, float]]],
    *,
    ks: Sequence[int] = DEFAULT_KS,
) -> RetrievalMetrics:
    """Mean each metric across questions, overall and per stratum.

    An empty input yields an empty :class:`RetrievalMetrics` rather than zeros-with-a-count,
    so a caller cannot mistake "no questions ran" for "quality is zero".
    """
    if not per_question:
        return RetrievalMetrics()

    metric_names = [f"{name}@{k}" for k in ks for name in ("recall", "hit_rate", "mrr", "ndcg")]
    totals = dict.fromkeys(metric_names, 0.0)
    stratum_totals: dict[str, dict[str, float]] = {}
    stratum_counts: dict[str, int] = {}

    for stratum, scores in per_question:
        for name in metric_names:
            totals[name] += scores.get(name, 0.0)
        bucket = stratum_totals.setdefault(stratum, dict.fromkeys(metric_names, 0.0))
        for name in metric_names:
            bucket[name] += scores.get(name, 0.0)
        stratum_counts[stratum] = stratum_counts.get(stratum, 0) + 1

    count = len(per_question)
    return RetrievalMetrics(
        question_count=count,
        recall_at_k={k: totals[f"recall@{k}"] / count for k in ks},
        hit_rate_at_k={k: totals[f"hit_rate@{k}"] / count for k in ks},
        mrr_at_k={k: totals[f"mrr@{k}"] / count for k in ks},
        ndcg_at_k={k: totals[f"ndcg@{k}"] / count for k in ks},
        by_stratum={
            stratum: {k: bucket[f"recall@{k}"] / stratum_counts[stratum] for k in ks}
            for stratum, bucket in sorted(stratum_totals.items())
        },
    )
