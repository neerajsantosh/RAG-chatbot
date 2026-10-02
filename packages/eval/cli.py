"""Evaluation CLI -- the command referenced by ``make eval``.

``python -m eval.cli --dataset <jsonl> [--gate] [--baseline <json>] [--out <file>]``

Exit codes are the contract: ``0`` means the run completed and every enabled gate passed,
``1`` means the gate failed, ``2`` means the run could not be performed (bad dataset,
missing baseline for ``--gate``). CI depends on the distinction -- a broken harness must not
look like a passing one.

With no index connected, the default is a null retriever, so the command reports zeros and
exits ``0``. That is M0's exit criterion and the first thing worth running.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from core.config import get_settings
from core.errors import AppError
from core.logging import get_logger
from eval.datasets import load_dataset
from eval.gate import compare_to_baseline, load_baseline, render_results, save_baseline
from eval.harness import EvalHarness
from eval.report import render_table, write_report

_logger = get_logger(__name__)

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_CANNOT_RUN = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval.cli",
        description="Run the RAG evaluation harness and optionally enforce the NFR-12 gate.",
    )
    parser.add_argument("--dataset", required=True, type=Path, help="path to a JSONL golden set")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("evals/baselines/current.json"),
        help="path to the stored baseline (default: evals/baselines/current.json)",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="compare against the baseline and exit non-zero on regression",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="record this run as the new baseline (refused if the gate fails)",
    )
    parser.add_argument("--out", type=Path, help="write a JSON report here")
    parser.add_argument("--out-format", choices=("json", "text"), default="json")
    parser.add_argument(
        "--json", action="store_true", help="print the report as JSON instead of a table"
    )
    parser.add_argument(
        "--phase",
        type=int,
        default=1,
        help="implementation phase; tolerances activate by phase (default: 1)",
    )
    parser.add_argument(
        "--config-version",
        default="phase1-unassigned",
        help="retrieval config version being evaluated (recorded on the baseline)",
    )
    parser.add_argument(
        "--prompt-version",
        default="phase1-unassigned",
        help="prompt version being evaluated (recorded on the baseline)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the table")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        dataset = load_dataset(args.dataset)
        settings = get_settings()

        harness = EvalHarness(dataset=dataset)
        report = replace(
            harness.run(),
            config_version=args.config_version,
            prompt_version=args.prompt_version,
            embedding_model=settings.embedding_model,
            llm_model=settings.chat_model,
        )

        if not args.quiet:
            if args.json:
                print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
            else:
                print(render_table(report))

        if args.out:
            destination = write_report(report, args.out, fmt=args.out_format)
            print(f"\nreport written to {destination}", file=sys.stderr)

        if args.gate:
            baseline = load_baseline(args.baseline)
            results = compare_to_baseline(report, baseline, phase=args.phase)
            print("\n" + render_results(results), file=sys.stderr)
            failed = [result for result in results if not result.passed]

            if failed and args.update_baseline:
                print(
                    "refusing to update the baseline: the gate is failing. Fix the regression "
                    "or record a deliberate decision; overwriting here is how gates stop "
                    "meaning anything.",
                    file=sys.stderr,
                )
                return EXIT_GATE_FAILED

            if args.update_baseline:
                save_baseline(args.baseline, report)
                print(f"baseline updated: {args.baseline}", file=sys.stderr)

            if failed:
                _logger.warning(
                    "evaluation gate failed",
                    extra={"failed_metrics": [r.metric for r in failed]},
                )
                return EXIT_GATE_FAILED

        return EXIT_OK

    except AppError as exc:
        # Typed errors carry a stable code; log it and keep the human message out of the
        # summary line since it may quote a dataset field.
        print(f"error [{exc.code}]: {exc.message}", file=sys.stderr)
        return EXIT_CANNOT_RUN


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
