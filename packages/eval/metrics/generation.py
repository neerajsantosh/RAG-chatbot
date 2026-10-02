"""Generation metrics -- not implemented in Phase 1.

This module exists and raises, rather than not existing at all. Phase 1's gate requires the
harness to run end to end on an empty index, and the temptation at that point is to return
``0.0`` for groundedness so the report looks complete. That is precisely the failure mode
worth engineering against: a zero that means "not measured" is indistinguishable from a
zero that means "measured, and it is bad", and the first thing anyone does with a suspicious
result is check the number.

Phase 5 implements these against a pinned judge (architecture §15.3): groundedness,
citation correctness, answer relevance, and unsupported-claim rate (G3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.errors import EvaluationNotImplemented

__all__ = ["GenerationMetrics", "citation_validity", "groundedness", "unsupported_claim_rate"]

IMPLEMENTED_IN = "implementation phase 5 (docs/implementation.md 7.3)"


def _not_implemented(metric: str) -> EvaluationNotImplemented:
    return EvaluationNotImplemented(
        f"{metric} is not implemented yet; scheduled for {IMPLEMENTED_IN}",
        details={"metric": metric},
    )


@dataclass(frozen=True, slots=True)
class GenerationMetrics:
    """Aggregate answer quality. Populated from phase 5."""

    groundedness: float = 0.0
    citation_validity: float = 0.0
    unsupported_claim_rate: float = 0.0
    answer_relevance: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "groundedness": self.groundedness,
            "citation_validity": self.citation_validity,
            "unsupported_claim_rate": self.unsupported_claim_rate,
            "answer_relevance": self.answer_relevance,
        }


def groundedness(answers: Sequence[str], contexts: Sequence[Sequence[str]]) -> float:
    """Fraction of answers whose claims are supported by the supplied context (G1).

    Answers: judge-rated, since only a model can say whether a claim is supported.
    """
    raise _not_implemented("groundedness")


def unsupported_claim_rate(answers: Sequence[str], contexts: Sequence[Sequence[str]]) -> float:
    """Fraction of answers containing at least one unsupported claim (G3, target <= 5%)."""
    raise _not_implemented("unsupported_claim_rate")


def citation_validity(
    answers: Sequence[str], supplied_chunk_ids: Sequence[frozenset[str]]
) -> float:
    """Fraction of citation markers that resolve to a supplied chunk id (G2, target 100%).

    Notably this one is deterministic rather than judged, and phase 5 implements it
    directly in :mod:`grounding.citations` without a model at all.
    """
    raise _not_implemented("citation_validity")
