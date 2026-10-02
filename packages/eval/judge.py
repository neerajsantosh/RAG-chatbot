"""LLM-as-judge -- disabled by default, unconfigured in Phase 1.

Judge-based metrics are corroborating evidence, never the primary signal, and they carry two
costs that make "on by default" the wrong answer:

* **Money and latency.** A 200-question set judged on every commit is an ongoing bill.
* **Drift.** A judge model that silently changes version moves every score, and the change
  looks exactly like a regression in the system under test. That is why
  :class:`JudgeConfig` pins a model *and* a version, and why the judge's agreement with
  human labels is itself a tracked metric (architecture §15.3).

Disabled by default via ``EVAL_JUDGE_ENABLED``. Enabling it without a pinned configuration
raises rather than silently proceeding, because an unpinned judge produces numbers nobody
can reproduce.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from core.errors import ConfigurationError, EvaluationNotImplemented
from llm.ports import ChatModel, Message

__all__ = ["JudgeConfig", "JudgeResult", "build_judge_messages", "judge_enabled"]

IMPLEMENTED_IN = "implementation phase 5 (docs/implementation.md 7.3)"

_GROUNDEDNESS_RUBRIC = """
You are grading whether an answer is supported by the supplied context.

Answer "grounded" only if every factual claim in the answer appears in the context.
Answer "ungrounded" if any claim goes beyond the context, even if it is true in general.

Context:
{context}

Answer:
{answer}

Reply with one word: grounded or ungrounded.
""".strip()

_CITATION_RUBRIC = """
You are grading whether each citation marker in an answer refers to the passage it is
attached to and supports the sentence it follows.

Answer "valid" only if every marker refers to a supporting passage.
Answer "invalid" if any marker is unsupported or points at the wrong passage.

Answer:
{answer}

Reply with one word: valid or invalid.
""".strip()


@dataclass(frozen=True, slots=True)
class JudgeConfig:
    """A pinned judge. The version is part of the identity, deliberately."""

    model_name: str
    model_version: str
    temperature: float = 0.0
    max_output_tokens: int = 8
    rubrics: dict[str, str] = field(default_factory=lambda: {
        "groundedness": _GROUNDEDNESS_RUBRIC,
        "citation_validity": _CITATION_RUBRIC,
    })

    @property
    def identity(self) -> str:
        """Recorded on every report so a score can be attributed to a judge."""
        return f"{self.model_name}@{self.model_version}"

    def validate(self) -> None:
        if not self.model_name or not self.model_version:
            raise ConfigurationError(
                "judge must pin both a model name and a model version; "
                "an unpinned judge produces scores nobody can reproduce",
                code="judge_unpinned",
            )


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """One judgement."""

    verdict: str
    judge: str
    rubric: str
    raw: str


def judge_enabled(enabled_in_settings: bool) -> bool:
    return enabled_in_settings


def build_judge_messages(config: JudgeConfig, rubric: str, **fields: str) -> list[Message]:
    """Render a rubric into chat messages.

    Judge input contains corpus text, so judge calls carry the same handling as production
    calls: never logged, never in a trace's detail payload, results stored as verdicts only.
    """
    if rubric not in config.rubrics:
        raise ConfigurationError(
            f"no rubric named {rubric!r}",
            code="judge_rubric_unknown",
            details={"rubrics": sorted(config.rubrics)},
        )
    template = config.rubrics[rubric]
    return [Message(role="user", content=template.format(**fields))]


def judge(model: ChatModel, config: JudgeConfig, rubric: str, **fields: str) -> JudgeResult:
    """Run one judgement.

    Raises until phase 5: there is no judge in Phase 1, and returning a verdict from a
    stub would put a fabricated number into a report.
    """
    raise EvaluationNotImplemented(
        f"judged metrics are not implemented yet; scheduled for {IMPLEMENTED_IN}",
        details={"rubric": rubric, "judge": config.identity},
    )


def agreement_with_human_labels(
    judgements: Sequence[JudgeResult], human_verdicts: Sequence[bool]
) -> float:
    """Fraction of judgements matching human labels.

    Tracked because a judge that has drifted is as dangerous as a regression in the system
    under test: both move the headline number for reasons that have nothing to do with
    quality.
    """
    raise EvaluationNotImplemented(
        f"judge calibration is not implemented yet; scheduled for {IMPLEMENTED_IN}",
        details={"judgements": len(judgements), "labels": len(human_verdicts)},
    )
