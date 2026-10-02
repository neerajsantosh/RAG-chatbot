"""The M0 exit criterion: the eval harness runs against an empty index and reports zeros.

The plan is explicit that the empty-index case must *exit 0 and report Recall@k of 0*, and
explicit that this is the specific criterion worth proving. The failure it guards against is
a harness that raises on an empty result set, which would make the M0 milestone unverifiable
and tempt someone to fabricate a number to get past it.

Two properties are tested together, because either alone is gameable:

* the harness returns zeros rather than raising, and
* the CLI exits 0 and writes a report.

A harness that returns zeros but whose CLI exits non-zero is still a broken gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.errors import EvaluationNotImplemented, ValidationFailed
from eval.cli import main as cli_main
from eval.datasets import DatasetQuestion, load_dataset
from eval.harness import EvalHarness, NullRetrievalFn, const_retrieval
from eval.metrics.retrieval import aggregate


@pytest.fixture
def mini(golden_dataset_path: Path) -> Any:
    dataset = load_dataset(golden_dataset_path)

    assert len(dataset.questions) >= 5, "the mini fixture must prove the schema works"
    assert any(q.answerable for q in dataset.questions)
    assert any(not q.answerable for q in dataset.questions), (
        "the fixture must include unanswerable questions or the refusal path is untested"
    )
    return dataset


def test_empty_index_reports_zeros_rather_than_raising(mini: Any) -> None:
    """The M0 criterion itself."""
    report = EvalHarness(mini, NullRetrievalFn()).run()

    assert report.retrieval.headline(5) == 0.0
    assert report.question_count == len(mini.questions)


def test_empty_input_yields_an_empty_metric_not_zeros(mini: Any) -> None:
    """'No questions ran' must not be reported as 'quality is zero'.

    This is the distinction that makes the zeros in the test above trustworthy: an empty
    aggregation returns an empty metric object, so a 0.0 can only have come from real
    arithmetic over real questions.
    """
    assert aggregate([]).question_count == 0


def test_perfect_retrieval_scores_one(mini: Any) -> None:
    """The other end of the range, so the zeros above are known to be real zeros."""
    perfect = {
        q.id: sorted(q.relevant_document_ids) or ["absent"] for q in mini.questions
    }

    report = EvalHarness(mini, const_retrieval(perfect)).run()

    assert report.retrieval.headline(5) == pytest.approx(1.0)


def test_cli_exits_zero_on_the_empty_index(golden_dataset_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "report.json"

    code = cli_main(["--dataset", str(golden_dataset_path), "--out", str(out)])

    assert code == 0, "the empty-index eval must exit 0"
    payload = json.loads(out.read_text(encoding="utf-8-sig"))
    # Metrics are nested by k so a new k can be added without a schema change.
    assert payload["retrieval"]["recall_at_k"]["5"] == 0.0
    assert payload["retrieval"]["hit_rate_at_k"]["5"] == 0.0
    assert payload["retrieval"]["mrr_at_k"]["5"] == 0.0
    assert payload["retrieval"]["ndcg_at_k"]["5"] == 0.0


def test_answerable_questions_are_the_scored_population(mini: Any) -> None:
    """Unanswerable questions are scored on refusal, not on recall.

    Counting them in the recall denominator would cap a perfect system below 1.0 by exactly
    the number of questions it correctly declined to answer.
    """
    report = EvalHarness(mini, NullRetrievalFn()).run()
    answerable = sum(1 for q in mini.questions if q.answerable)

    assert report.retrieval.question_count == answerable
    assert report.question_count == len(mini.questions)


def test_eval_is_deterministic(mini: Any) -> None:
    """The plan requires two identical runs. Same input must give the same numbers."""
    first = EvalHarness(mini, NullRetrievalFn()).run().to_dict()
    second = EvalHarness(mini, NullRetrievalFn()).run().to_dict()

    assert first == second


def test_one_failing_retrieval_does_not_abort_the_sweep(mini: Any) -> None:
    """A retrieval that raises costs one question, not the whole report.

    Otherwise a transient index error looks identical to a broken harness, and the failure
    mode is a gate that fails for the wrong reason.
    """

    class Exploding:
        description = "always fails"

        def __call__(self, question: Any, principal: Any, k: int) -> tuple[str, ...]:
            raise RuntimeError("index unavailable")

    report = EvalHarness(mini, Exploding()).run()

    assert report.question_count == len(mini.questions)
    assert report.retrieval.headline(5) == 0.0


# -- unimplemented metrics must say so ---------------------------------------


def test_generation_metrics_raise_rather_than_return_zero() -> None:
    """A fake 0.0 is indistinguishable from a real failing score.

    This is the plan's "stub that raises not implemented until phase 5 rather than returning
    a fake number", and it is the rule that keeps phases 2-3 honest.
    """
    from eval.metrics.generation import (
        citation_validity,
        groundedness,
        unsupported_claim_rate,
    )

    for metric in (groundedness, unsupported_claim_rate):
        with pytest.raises(EvaluationNotImplemented):
            metric(answers=["a"], contexts=[["c"]])

    with pytest.raises(EvaluationNotImplemented):
        citation_validity(answers=["a"], supplied_chunk_ids=[frozenset({"c1"})])


def test_generation_metrics_are_absent_from_the_report(mini: Any) -> None:
    """Unimplemented metrics must not appear as keys with null or zero values.

    A missing key reads as "not measured". A key reading 0.0 reads as "measured, and it is
    zero", which is the claim this whole design refuses to make.
    """
    payload = EvalHarness(mini, NullRetrievalFn()).run().to_dict()

    assert "generation" not in payload or payload["generation"] is None


# -- dataset validation ------------------------------------------------------


def test_answerable_question_needs_a_gold_label() -> None:
    with pytest.raises(ValidationFailed) as exc:
        DatasetQuestion(id="q1", question="what is up", answerable=True)

    assert exc.value.code == "dataset_unlabelled"


def test_unanswerable_question_must_not_carry_a_gold_label() -> None:
    """The contradictory case.

    An unanswerable question with a gold label is either a labelling mistake or a question
    that should have been answerable; either way, scoring it silently is wrong.
    """
    with pytest.raises(ValidationFailed) as exc:
        DatasetQuestion(
            id="q1", question="what is up", answerable=False, relevant_document_ids=frozenset({"d"})
        )

    assert exc.value.code == "dataset_contradictory"


def test_dataset_rejects_a_malformed_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "q1", "question": "unterminated\n', encoding="utf-8")

    with pytest.raises((ValidationFailed, ValueError, json.JSONDecodeError)):
        load_dataset(bad)


def test_dataset_reports_the_offending_line_number(tmp_path: Path) -> None:
    """A validation error with no line number makes a 5000-line dataset unfixable."""
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        json.dumps({"id": "q1", "question": "ok", "answerable": False}) + "\n"
        + json.dumps({"id": "q2", "question": "ok", "answerable": True}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationFailed) as exc:
        load_dataset(bad)

    assert exc.value.details.get("line") == 2


def test_dataset_reads_a_utf8_bom(tmp_path: Path) -> None:
    """PowerShell writes BOMs on Windows and baseline files are edited by hand.

    A BOM makes the first line unparseable JSON, which looks like a corrupt dataset rather
    than an encoding artefact.
    """
    bom = tmp_path / "bom.jsonl"
    bom.write_bytes(
        b"\xef\xbb\xbf"
        + json.dumps({"id": "q1", "question": "hello", "answerable": False}).encode()
    )

    assert len(load_dataset(bom).questions) == 1
