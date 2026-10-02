"""Report rendering.

Two formats from one result: JSON for the CI gate and trend storage, and a readable table
for a person deciding whether to ship. Both name the configuration versions and the dataset
version, because a metric without them is not reproducible -- which is NFR-13 applied to
evaluation rather than to answers.

The per-stratum table is printed by default. An aggregate number alone hides the case that
matters: 0.80 overall while the multi-document stratum sits at 0.30.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.errors import ValidationFailed
from eval.metrics.retrieval import RetrievalMetrics

__all__ = ["EvalReport", "render_table", "write_report"]


@dataclass(frozen=True, slots=True)
class EvalReport:
    """One evaluation run."""

    dataset_name: str
    dataset_version: str
    dataset_path: str = ""
    question_count: int = 0
    retrieval: RetrievalMetrics = field(default_factory=RetrievalMetrics)
    config_version: str = "unset"
    prompt_version: str = "unset"
    embedding_model: str = "unset"
    llm_model: str = "unset"
    unanswerable_refusals: dict[str, float] = field(default_factory=dict)
    failures: Sequence[dict[str, Any]] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": {
                "name": self.dataset_name,
                "version": self.dataset_version,
                "path": self.dataset_path,
                "question_count": self.question_count,
            },
            "versions": {
                "config_version": self.config_version,
                "prompt_version": self.prompt_version,
                "embedding_model": self.embedding_model,
                "llm_model": self.llm_model,
            },
            "retrieval": self.retrieval.to_dict(),
            "unanswerable_refusals": self.unanswerable_refusals,
            "failures": list(self.failures),
        }

    def summary_line(self, k: int = 5) -> str:
        return (
            f"{self.dataset_name}: recall@{k}={self.retrieval.headline(k):.4f} "
            f"over {self.question_count} question(s)"
        )


def render_table(report: EvalReport, *, ks: Sequence[int] = (1, 5, 10)) -> str:
    """Render a report as a readable table."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"dataset      {report.dataset_name} ({report.dataset_version})")
    lines.append(f"questions    {report.question_count}")
    lines.append(f"config       {report.config_version}")
    lines.append(f"prompt       {report.prompt_version}")
    lines.append(f"embeddings   {report.embedding_model}")
    lines.append(f"llm          {report.llm_model}")
    lines.append("=" * 72)
    lines.append("")

    if report.question_count == 0:
        lines.append("no questions were run")
        return "\n".join(lines)

    lines.append(f"{'metric':<16}" + "".join(f"{'at ' + str(k):>12}" for k in ks))
    lines.append("-" * 72)
    for label, values in (
        ("recall", report.retrieval.recall_at_k),
        ("hit_rate", report.retrieval.hit_rate_at_k),
        ("mrr", report.retrieval.mrr_at_k),
        ("ndcg", report.retrieval.ndcg_at_k),
    ):
        rendered = "".join(f"{values.get(k, 0.0):>12.4f}" for k in ks)
        lines.append(f"{label:<16}{rendered}")

    if report.retrieval.by_stratum:
        lines.append("")
        lines.append("recall@5 by stratum")
        lines.append("-" * 72)
        width = max(len(name) for name in report.retrieval.by_stratum)
        for stratum, values in report.retrieval.by_stratum.items():
            lines.append(f"{stratum:<{width}}  {values.get(5, 0.0):.4f}")

    if report.unanswerable_refusals:
        lines.append("")
        lines.append("refusal correctness")
        lines.append("-" * 72)
        width = max(len(name) for name in report.unanswerable_refusals)
        for name, value in report.unanswerable_refusals.items():
            lines.append(f"{name:<{width}}  {value:.4f}")

    if report.failures:
        lines.append("")
        lines.append(f"failed questions ({len(report.failures)})")
        lines.append("-" * 72)
        for failure in report.failures:
            lines.append(f"  {failure.get('id', '?')}: {failure.get('reason', 'unknown')}")

    return "\n".join(lines)


def write_report(report: EvalReport, path: str | Path, *, fmt: str = "json") -> Path:
    """Write a report to disk.

    ``fmt`` is ``json`` for CI consumption or ``text`` for a human-readable artefact
    committed alongside a release note.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        payload = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    elif fmt == "text":
        payload = render_table(report) + "\n"
    else:
        raise ValidationFailed(
            f"unsupported report format {fmt!r}; expected 'json' or 'text'",
            code="report_format_unknown",
        )

    destination.write_text(payload, encoding="utf-8")
    return destination
