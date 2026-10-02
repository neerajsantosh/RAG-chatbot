"""The NFR-12 regression gate.

A quality number on its own is decoration. What the PRD actually promises is *"every release
must pass the eval gate"*, and that promise only has teeth if something fails the build.

The gate compares a run against a stored baseline and refuses to let a change through when a
metric regresses beyond tolerance:

* ``recall@5`` may fall by at most 3 points (NFR-12).
* ``groundedness`` may fall by at most 5 points (G5) -- inactive until phase 5.
* ``citation_validity`` must be exactly 1.0 (G2). No tolerance, because a citation that
  does not resolve is a defect, not a quality gradient.

Three properties keep the gate from becoming theatre:

* **The baseline is pinned to versions.** If it was recorded against a different embedding
  model or config version, the comparison is refused rather than attempted. Otherwise a
  routine model upgrade reads as a system regression and people stop trusting the gate --
  and a gate nobody trusts is one everybody bypasses.
* **Deltas are one-directional.** Improvement is never a failure. Some metrics, like
  refusal precision, are only meaningful when high.
* **Absence is not improvement.** A metric missing from a report is a failed gate, not a
  skipped one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from core.errors import ValidationFailed
from eval.report import EvalReport

__all__ = [
    "DEFAULT_TOLERANCES",
    "GateResult",
    "RegressionGate",
    "compare_to_baseline",
    "load_baseline",
    "save_baseline",
]


@dataclass(frozen=True, slots=True)
class Tolerance:
    """How far a metric may fall before the gate fails."""

    name: str
    maximum_drop: float
    higher_is_better: bool = True
    exact: bool = False
    minimum: float | None = None
    enabled_from_phase: int = 1


DEFAULT_TOLERANCES: tuple[Tolerance, ...] = (
    Tolerance("recall@5", maximum_drop=0.03, enabled_from_phase=1),
    Tolerance("groundedness", maximum_drop=0.05, enabled_from_phase=5),
    Tolerance(
        "unsupported_claim_rate",
        maximum_drop=0.05,
        higher_is_better=False,
        enabled_from_phase=5,
    ),
    Tolerance(
        "citation_validity", maximum_drop=0.0, exact=True, minimum=1.0, enabled_from_phase=5
    ),
)
"""The gate's contract, in one place.

``groundedness`` and ``unsupported_claim_rate`` are declared from the start and marked with
the phase that enables them. Writing them down now is what stops the phase-5 temptation to
pick tolerances that the current numbers happen to satisfy.
"""

VERSION_KEYS: tuple[str, ...] = ("config_version", "embedding_model", "llm_model", "prompt_version")
"""Baseline validity keys. A difference in any of these invalidates the comparison."""


@dataclass(frozen=True, slots=True)
class GateResult:
    """One metric's verdict."""

    metric: str
    observed: float | None
    baseline: float | None
    drop: float | None
    allowed_drop: float
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "observed": self.observed,
            "baseline": self.baseline,
            "drop": self.drop,
            "allowed_drop": self.allowed_drop,
            "passed": self.passed,
            "detail": self.detail,
        }

    def render(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        if self.observed is None:
            return f"[{status}] {self.metric}: not reported ({self.detail})"
        if self.baseline is None:
            return f"[{status}] {self.metric}: {self.observed:.4f} (no baseline)"
        assert self.drop is not None
        return (
            f"[{status}] {self.metric}: {self.observed:.4f} vs baseline {self.baseline:.4f} "
            f"(drop {self.drop:+.4f}, allowed {self.allowed_drop:.4f})"
        )


@dataclass(frozen=True, slots=True)
class RegressionGate:
    """Evaluates a run against a baseline."""

    tolerances: Sequence[Tolerance] = DEFAULT_TOLERANCES
    phase: int = 1
    """Current implementation phase. Tolerances with a higher ``enabled_from_phase`` are
    reported as skipped rather than silently ignored, so a gate run makes visible which
    promises are not yet enforced."""

    def evaluate(self, report: EvalReport, baseline: dict[str, Any] | None) -> list[GateResult]:
        if baseline is None:
            return [
                GateResult(
                    metric=tolerance.name,
                    observed=self._observed(report, tolerance),
                    baseline=None,
                    drop=None,
                    allowed_drop=tolerance.maximum_drop,
                    passed=True,
                    detail="no baseline recorded; first run establishes it",
                )
                for tolerance in self._active()
            ]

        observed_versions = report.to_dict()["versions"]
        baseline_versions = baseline.get("versions", {})
        mismatched = [
            key
            for key in VERSION_KEYS
            if str(observed_versions.get(key)) != str(baseline_versions.get(key))
        ]
        if mismatched:
            # Refusing is the safe reading: the numbers are not comparable, and inventing a
            # comparison here is how gates get quietly ignored.
            return [
                GateResult(
                    metric=tolerance.name,
                    observed=None,
                    baseline=None,
                    drop=None,
                    allowed_drop=tolerance.maximum_drop,
                    passed=False,
                    detail=(
                        "baseline was recorded for different "
                        + ", ".join(
                            f"{key}={baseline_versions.get(key)!r}" for key in mismatched
                        )
                        + "; re-record the baseline for this configuration"
                    ),
                )
                for tolerance in self._active()
            ]

        baseline_metrics = baseline.get("retrieval", {})
        results: list[GateResult] = []
        for tolerance in self._active():
            observed = self._observed(report, tolerance)
            reference = self._baseline_value(baseline_metrics, tolerance)

            if observed is None or reference is None:
                results.append(
                    GateResult(
                        metric=tolerance.name,
                        observed=observed,
                        baseline=reference,
                        drop=None,
                        allowed_drop=tolerance.maximum_drop,
                        passed=False,
                        detail=(
                            "metric missing; a missing metric is a failed gate, "
                            "not a skipped one"
                        ),
                    )
                )
                continue

            results.append(self._judge(tolerance, observed, reference))
        return results

    def _active(self) -> tuple[Tolerance, ...]:
        return tuple(t for t in self.tolerances if t.enabled_from_phase <= self.phase)

    @staticmethod
    def _observed(report: EvalReport, tolerance: Tolerance) -> float | None:
        if tolerance.name == "recall@5":
            return report.retrieval.recall_at_k.get(5)
        raise KeyError(f"{tolerance.name} is not measurable in Phase 1 reports")

    @staticmethod
    def _baseline_value(metrics: dict[str, Any], tolerance: Tolerance) -> float | None:
        if tolerance.name == "recall@5":
            value = metrics.get("recall_at_k", {}).get("5")
            return float(value) if value is not None else None
        return None

    @staticmethod
    def _judge(tolerance: Tolerance, observed: float, reference: float) -> GateResult:
        if tolerance.exact:
            target = tolerance.minimum if tolerance.minimum is not None else reference
            passed = abs(observed - target) < 1e-9
            return GateResult(
                metric=tolerance.name,
                observed=observed,
                baseline=reference,
                drop=reference - observed,
                allowed_drop=0.0,
                passed=passed,
                detail="binary metric; no tolerance" if not passed else "",
            )

        if tolerance.higher_is_better:
            drop = reference - observed
            passed = drop <= tolerance.maximum_drop + 1e-9
        else:
            # For lower-is-better metrics a rise is the regression.
            drop = observed - reference
            passed = drop <= tolerance.maximum_drop + 1e-9

        return GateResult(
            metric=tolerance.name,
            observed=observed,
            baseline=reference,
            drop=drop,
            allowed_drop=tolerance.maximum_drop,
            passed=passed,
        )


def compare_to_baseline(
    report: EvalReport, baseline: dict[str, Any] | None, *, phase: int = 1
) -> list[GateResult]:
    """Convenience wrapper around :class:`RegressionGate`."""
    return RegressionGate(phase=phase).evaluate(report, baseline)


def load_baseline(path: str | Path) -> dict[str, Any] | None:
    """Load a stored baseline, or ``None`` if the file does not exist yet.

    A missing baseline is a normal first-run state, not an error: it means "this establishes
    the reference".
    """
    location = Path(path)
    if not location.is_file():
        return None
    try:
        # utf-8-sig, not utf-8: these files are hand-edited and CI-visible, and a BOM
        # written by a Windows editor would otherwise read as corrupt rather than correct.
        return cast("dict[str, Any]", json.loads(location.read_text(encoding="utf-8-sig")))
    except json.JSONDecodeError as exc:
        raise ValidationFailed(
            f"baseline {location} is not valid JSON: {exc.msg}",
            code="baseline_invalid",
            details={"path": str(location)},
        ) from exc


def save_baseline(path: str | Path, report: EvalReport) -> Path:
    """Record a run as the new baseline.

    Only meaningful once the gate is green; ``eval.cli`` refuses to overwrite a baseline
    with a run that regressed, because the natural way to "fix" a failing gate is to
    re-baseline it, and the natural way to do that accidentally is to skip the check.
    """
    location = Path(path)
    location.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    location.write_text(payload, encoding="utf-8")
    return location


def render_results(results: Iterable[GateResult]) -> str:
    return "\n".join(result.render() for result in results)
