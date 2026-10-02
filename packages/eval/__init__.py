"""Evaluation harness.

Its distinguishing property is that it runs before there is anything to evaluate. Phase 1
ships it wired to an empty index and it must exit cleanly reporting zeros -- that is the PRD
M0 exit criterion, and it is what guarantees the release gate exists *before* the system
that it gates.

Two rules the module enforces on itself:

* **Deterministic metrics first.** Recall, MRR and nDCG are computed here with no model in
  the loop. Judged metrics (groundedness, citation correctness) are corroborating evidence
  and are added in phase 5, behind a pinned judge.
* **Never a placeholder number.** A metric that is not implemented raises
  :class:`~core.errors.EvaluationNotImplemented` rather than returning ``0.0``. A silent
  zero in a report is indistinguishable from a real regression, which is the single most
  dangerous failure mode an evaluation harness can have.
"""

from eval.datasets import Dataset, DatasetQuestion, load_dataset, validate_records
from eval.gate import GateResult, RegressionGate, compare_to_baseline
from eval.harness import EvalHarness, NullRetrievalFn, RetrievalFn
from eval.report import EvalReport, write_report

__all__ = [
    "Dataset",
    "DatasetQuestion",
    "EvalHarness",
    "EvalReport",
    "GateResult",
    "NullRetrievalFn",
    "RegressionGate",
    "RetrievalFn",
    "compare_to_baseline",
    "load_dataset",
    "validate_records",
    "write_report",
]
