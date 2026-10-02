"""Metrics.

Retrieval metrics are deterministic and available now. Generation metrics raise until phase
5 -- see :mod:`eval.metrics.generation` for why returning a placeholder zero would be worse
than an explicit failure.
"""

from eval.metrics.retrieval import (
    DEFAULT_KS,
    RetrievalMetrics,
    aggregate,
    ndcg_at_k,
    oracle_union_recall,
    per_question_recall,
    score_question,
)

__all__ = [
    "DEFAULT_KS",
    "RetrievalMetrics",
    "aggregate",
    "ndcg_at_k",
    "oracle_union_recall",
    "per_question_recall",
    "score_question",
]
