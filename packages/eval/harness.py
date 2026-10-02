"""The harness itself.

Ties a dataset to a retrieval function and produces a report. The design point that matters
for Phase 1 is :class:`NullRetrievalFn`: retrieval is *pluggable*, and the default
implementation returns nothing. So the harness runs today against an empty index, exits
zero, and reports zeros -- proving the plumbing before there is anything to measure.

That ordering is deliberate. A harness that only appears alongside a real retriever is a
harness that gets built under deadline at the point where it is needed to catch a regression,
which is the wrong moment to design one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, runtime_checkable

from core.auth.principal import Principal
from eval.datasets import Dataset, DatasetQuestion
from eval.metrics.retrieval import (
    DEFAULT_KS,
    RetrievalMetrics,
    aggregate,
    oracle_union_recall,
    score_question,
)
from eval.report import EvalReport

__all__ = ["EvalHarness", "NullRetrievalFn", "RetrievalFn", "RetrievalOutcome"]


@runtime_checkable
class RetrievalFn(Protocol):
    """Returns ranked chunk or document ids for a question.

    Ids, not chunk text: the harness measures *which* content was found, and must never be
    handed corpus text it would then be tempted to log or embed in a report.
    """

    def __call__(
        self, question: DatasetQuestion, *, principal: Principal, k: int
    ) -> Sequence[str]:
        ...


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """One retriever's answer, plus enough context to report on it."""

    ids: tuple[str, ...]
    refused: bool = False


class NullRetrievalFn:
    """Returns nothing for every question.

    The Phase 1 default. Recall is legitimately 0.0 against an empty index, and the harness
    must report that rather than refusing to run -- the distinction the gate checks is
    "exits zero and reports zeros", not "reports something positive".
    """

    __slots__ = ("_description",)

    def __init__(self, description: str = "null retrieval: no index is connected") -> None:
        self._description = description

    @property
    def description(self) -> str:
        return self._description

    def __call__(
        self, question: DatasetQuestion, *, principal: Principal, k: int
    ) -> Sequence[str]:
        return ()

    def rank_list(
        self, question: DatasetQuestion, *, principal: Principal, k: int
    ) -> Sequence[str]:
        return self(question, principal=principal, k=k)


@dataclass
class EvalHarness:
    """Runs a dataset against one or more retrievers."""

    dataset: Dataset
    retrieval: RetrievalFn = field(default_factory=NullRetrievalFn)
    secondary_retrieval: RetrievalFn | None = None
    principal: Principal = field(
        default_factory=lambda: Principal(user_id="eval", roles=frozenset({"operator"}))
    )
    ks: Sequence[int] = DEFAULT_KS
    max_failures_recorded: int = 25
    """A cap on recorded failures. A run where everything fails would otherwise produce a
    report larger than the dataset it evaluated."""

    def run(self) -> EvalReport:
        per_question: list[tuple[str, dict[str, float]]] = []
        failures: list[dict[str, Any]] = []
        refusals: list[tuple[str, bool]] = []
        union_scores: list[float] = []
        k = max(self.ks)

        for question in self.dataset:
            try:
                ranked = tuple(self.retrieval(question, principal=self.principal, k=k))
            except Exception as exc:  # noqa: BLE001 - one bad question must not abort the run
                if len(failures) < self.max_failures_recorded:
                    failures.append(
                        {
                            "id": question.id,
                            "stratum": question.stratum,
                            "reason": f"{type(exc).__name__}: {exc}",
                        }
                    )
                ranked = ()

            if not question.answerable:
                refused = self._was_refused(question, ranked)
                refusals.append((question.id, refused))
                continue

            gold = question.gold_ids()
            scores = score_question(ranked, gold, ks=self.ks)
            per_question.append((question.stratum, scores))

            if self.secondary_retrieval is not None:
                secondary = tuple(
                    self.secondary_retrieval(question, principal=self.principal, k=k)
                )
                union_scores.append(
                    oracle_union_recall((list(ranked), list(secondary)), gold, k)
                )

        metrics = aggregate(per_question, ks=self.ks)
        metrics = self._attach_union(metrics, union_scores)

        return EvalReport(
            dataset_name=self.dataset.name,
            dataset_version=self.dataset.version,
            dataset_path=str(self.dataset.path or ""),
            question_count=len(self.dataset),
            retrieval=metrics,
            unanswerable_refusals=self._refusal_report(refusals),
            failures=tuple(failures),
        )

    def _was_refused(self, question: DatasetQuestion, ranked: Sequence[str]) -> bool:
        """Whether the pipeline declined to answer an unanswerable question.

        Phase 1 has no pipeline, so absence of results counts as a correct refusal. That is
        the right default: with nothing retrieved, refusing is the only correct behaviour,
        and it keeps the refusal metric meaningful as the pipeline is built up.
        """
        return len(ranked) == 0

    @staticmethod
    def _attach_union(metrics: RetrievalMetrics, union_scores: Sequence[float]) -> RetrievalMetrics:
        if not union_scores:
            return metrics
        return replace(metrics, oracle_union=sum(union_scores) / len(union_scores))

    @staticmethod
    def _refusal_report(refusals: Sequence[tuple[str, bool]]) -> dict[str, float]:
        if not refusals:
            return {}
        correct = sum(1 for _, refused in refusals if refused)
        return {
            "unanswerable_total": float(len(refusals)),
            "correct_refusal_rate": round(correct / len(refusals), 6),
        }


def const_retrieval(ids_by_question: dict[str, Sequence[str]]) -> Callable[..., Sequence[str]]:
    """Build a fixed retrieval function. Used by tests to exercise known rankings."""

    def retrieve(question: DatasetQuestion, *, principal: Principal, k: int) -> Sequence[str]:
        return tuple(ids_by_question.get(question.id, ()))[:k]

    return retrieve
