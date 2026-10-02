"""Dataset format and loading.

The labelled question set is the foundation of every quality claim in the PRD (NFR-11), and
the riskiest artefact in the repository to produce: it needs someone who knows the corpus.
The format is therefore plain JSONL -- reviewable in a diff, editable without a tool, and
diffable in a pull request where disagreements about a label are actually visible.

A record is only useful if the label is honest about *which* document answers the question.
``relevant_chunk_ids`` is optional because labelling chunks is expensive; a document-level
label still catches the catastrophic failure of retrieving the wrong document, which is the
one that matters most.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from core.errors import ValidationFailed

__all__ = [
    "DEFAULT_STRATA",
    "Dataset",
    "DatasetQuestion",
    "load_dataset",
    "validate_records",
]

DEFAULT_STRATA: Final[tuple[str, ...]] = (
    "exact_term",
    "natural_language",
    "multi_document",
    "synonym",
    "unanswerable",
)
"""Strata the golden set must cover. Reported separately, never only in aggregate.

An aggregate recall of 0.80 can mean "uniformly acceptable" or "perfect on easy facts and
useless on the hard half". Operators need to know which, so ``--by-stratum`` reporting is
not optional.
"""


@dataclass(frozen=True, slots=True)
class DatasetQuestion:
    """One labelled question."""

    id: str
    question: str
    answerable: bool = True
    relevant_document_ids: frozenset[str] = field(default_factory=frozenset)
    relevant_chunk_ids: frozenset[str] = field(default_factory=frozenset)
    stratum: str = "natural_language"
    notes: str = ""

    def __post_init__(self) -> None:
        if self.answerable and not (self.relevant_document_ids or self.relevant_chunk_ids):
            raise ValidationFailed(
                f"dataset question {self.id!r} is marked answerable but has no gold label",
                code="dataset_unlabelled",
                details={"id": self.id},
            )
        if not self.answerable and (self.relevant_document_ids or self.relevant_chunk_ids):
            raise ValidationFailed(
                f"dataset question {self.id!r} is marked unanswerable but carries a gold label",
                code="dataset_contradictory",
                details={"id": self.id},
            )

    def gold_ids(self) -> frozenset[str]:
        """Everything a correct retrieval must return."""
        return self.relevant_document_ids | self.relevant_chunk_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "answerable": self.answerable,
            "relevant_document_ids": sorted(self.relevant_document_ids),
            "relevant_chunk_ids": sorted(self.relevant_chunk_ids),
            "stratum": self.stratum,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class Dataset:
    """A loaded, validated dataset."""

    name: str
    questions: tuple[DatasetQuestion, ...]
    version: str = "unversioned"
    path: Path | None = None

    def __len__(self) -> int:
        return len(self.questions)

    def __iter__(self) -> Iterator[DatasetQuestion]:
        return iter(self.questions)

    @property
    def strata(self) -> tuple[str, ...]:
        return tuple(sorted({item.stratum for item in self.questions}))

    def by_stratum(self, stratum: str) -> tuple[DatasetQuestion, ...]:
        return tuple(item for item in self.questions if item.stratum == stratum)

    @property
    def answerable(self) -> tuple[DatasetQuestion, ...]:
        return tuple(item for item in self.questions if item.answerable)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "count": len(self.questions),
            "answerable": len(self.answerable),
            "unanswerable": len(self.questions) - len(self.answerable),
            "strata": list(self.strata),
        }


def _parse_record(raw: dict[str, Any], *, source: str, line_number: int) -> DatasetQuestion:
    def fail(message: str, code: str) -> ValidationFailed:
        return ValidationFailed(
            f"{source}:{line_number}: {message}",
            code=code,
            details={"source": source, "line": line_number},
        )

    if not isinstance(raw, dict):
        raise fail("record must be a JSON object", "dataset_record_invalid")

    missing = [key for key in ("id", "question") if key not in raw]
    if missing:
        raise fail(f"record is missing required field(s): {missing}", "dataset_field_missing")

    try:
        return DatasetQuestion(
            id=str(raw["id"]),
            question=str(raw["question"]),
            answerable=bool(raw.get("answerable", True)),
            relevant_document_ids=frozenset(raw.get("relevant_document_ids") or ()),
            relevant_chunk_ids=frozenset(raw.get("relevant_chunk_ids") or ()),
            stratum=str(raw.get("stratum", "natural_language")),
            notes=str(raw.get("notes", "")),
        )
    except ValidationFailed as exc:
        # DatasetQuestion validates in __post_init__ and raises without knowing where the
        # record came from. Re-raised here with the source and line attached, because the
        # semantic errors (unlabelled, contradictory) are the common ones and a
        # "dataset_unlabelled" with no line number is unfixable in a 5000-line golden set.
        raise ValidationFailed(
            f"{source}:{line_number}: {exc.message}",
            code=exc.code,
            details={**exc.details, "source": source, "line": line_number},
        ) from exc


def validate_records(records: Sequence[dict[str, Any]], *, source: str = "<memory>") -> None:
    """Validate without loading. Used by CI on the committed golden set."""
    seen: set[str] = set()
    for index, raw in enumerate(records, start=1):
        question = _parse_record(raw, source=source, line_number=index)
        if question.id in seen:
            raise ValidationFailed(
                f"{source}: duplicate question id {question.id!r}",
                code="dataset_duplicate_id",
                details={"id": question.id},
            )
        seen.add(question.id)


def load_dataset(path: str | Path) -> Dataset:
    """Load and validate a JSONL dataset.

    Duplicate ids are an error rather than a warning. A duplicated label silently doubles
    its weight in every aggregate, which is the kind of error that makes a reported
    improvement partly fictional.
    """
    location = Path(path)
    if not location.is_file():
        raise ValidationFailed(
            f"dataset not found: {location}",
            code="dataset_missing",
            details={"path": str(location)},
        )

    questions: list[DatasetQuestion] = []
    seen: set[str] = set()

    # utf-8-sig tolerates a BOM, which Windows editors add to files people hand-edit.
    with location.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValidationFailed(
                    f"{location}:{line_number}: invalid JSON ({exc.msg})",
                    code="dataset_invalid_json",
                    details={"path": str(location), "line": line_number},
                ) from exc

            question = _parse_record(raw, source=str(location), line_number=line_number)
            if question.id in seen:
                raise ValidationFailed(
                    f"{location}: duplicate question id {question.id!r} on line {line_number}",
                    code="dataset_duplicate_id",
                    details={"path": str(location), "id": question.id},
                )
            seen.add(question.id)
            questions.append(question)

    if not questions:
        raise ValidationFailed(
            f"{location}: dataset contains no questions",
            code="dataset_empty",
            details={"path": str(location)},
        )

    stem = location.stem
    version = stem.rsplit("-", 1)[1] if "-" in stem else "unversioned"

    return Dataset(name=stem, questions=tuple(questions), version=version, path=location)
