"""NFR-16: no document or user content in logs.

The plan singles this out: "run a test that logs a field named `question`; the redaction
filter strips it". These are negative tests -- the assertion that matters is that a planted
marker never appears in the emitted output.

The strategy being tested is **default deny**: a field keeps its exact value only if it is on
:data:`~core.logging.redaction.SAFE_FIELD_NAMES`. Everything else is either replaced by
:data:`~core.logging.redaction.REDACTED` (content) or summarised by type (unknown). The
tests below pin all three outcomes, because the third one is the one that surprises people:
an unrecognised field does *not* pass through just because nobody thought of it.

``tools/check_log_hygiene.py`` also scans this file, so the planted markers below are what
keep that check non-vacuous.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from core.logging import configure_logging, get_logger, log_extra
from core.logging.redaction import (
    REDACTED,
    RedactionFilter,
    is_content_field,
    is_safe_field,
    redact_mapping,
    redact_value,
)

CONTENT_MARKER = "s3cr3t-user-question-text"
"""Planted user content. Must never appear in any emitted line."""


@pytest.fixture
def emit() -> Iterator[Any]:
    """Emit records through a real configured handler and hand back the output."""
    buffer = io.StringIO()
    configure_logging(level="DEBUG", fmt="json", stream=buffer, redact=True)

    def emit_message(**fields: Any) -> str:
        get_logger("rag.test.loghygiene").info("chat turn", extra=log_extra(**fields))
        return buffer.getvalue().strip().splitlines()[-1]

    try:
        yield emit_message
    finally:
        # Leave the root logger clean so later tests are not affected.
        logging.getLogger().handlers.clear()


# -- the field the plan names explicitly -------------------------------------


def test_field_named_question_is_stripped(emit: Any) -> None:
    line = emit(question=CONTENT_MARKER)

    assert CONTENT_MARKER not in line
    fields = json.loads(line)["fields"]
    assert fields["question"] == REDACTED, (
        "the key should survive so a reader can tell the field was populated; only the "
        "value is replaced"
    )


def test_content_marker_never_reaches_json_output(emit: Any) -> None:
    line = emit(
        question=CONTENT_MARKER,
        document_text=CONTENT_MARKER,
        answer=CONTENT_MARKER,
        retrieved_text=CONTENT_MARKER,
        prompt=CONTENT_MARKER,
        completion=CONTENT_MARKER,
        snippet=CONTENT_MARKER,
    )

    assert CONTENT_MARKER not in line, f"content leaked into JSON output: {line}"


def test_content_under_an_unexpected_key_is_still_removed(emit: Any) -> None:
    """Marker-based matching, so a differently-named key does not become a way through.

    ``some_unexpected_name`` is not on the content list, but it is not on the allow-list
    either -- so it is summarised by type. That is the point of default deny.
    """
    line = emit(some_unexpected_name=CONTENT_MARKER)

    assert CONTENT_MARKER not in line
    assert json.loads(line)["fields"]["some_unexpected_name"].startswith("<str")


def test_operational_fields_keep_their_values(emit: Any) -> None:
    """A log where everything is redacted is not a log.

    ``chunk_count`` survives on a technicality worth stating: it is not allow-listed, but
    ``redact_value`` passes numbers through unchanged, so a count is still readable. If a
    count ever has to be redacted, the fix belongs in the allow-list, not in the formatter.
    """
    line = emit(
        request_id="req_abc123",
        status_code=200,
        duration_ms=12.5,
        chunk_count=7,
        chat_model="fake",
        embedding_model_version="unassigned",
    )

    fields = json.loads(line)["fields"]
    assert fields["request_id"] == "req_abc123"
    assert fields["status_code"] == 200
    assert fields["duration_ms"] == 12.5
    assert fields["chunk_count"] == 7
    assert fields["chat_model"] == "fake"
    assert fields["embedding_model_version"] == "unassigned"


# -- the guard demonstrably fails when removed --------------------------------


def test_redaction_can_be_disabled_and_then_leaks(emitted_unfiltered: Any) -> None:
    """The plan's gate: a deliberately unfiltered logger fails the check.

    Asserting both halves matters. A test that only shows redaction working cannot
    distinguish a working filter from a logger that never received the content.
    """
    line = emitted_unfiltered(question=CONTENT_MARKER)

    assert CONTENT_MARKER in line, (
        "configure_logging(redact=False) is supposed to emit the raw value; if it does not, "
        "the redaction tests prove nothing because the content never reached the handler"
    )


@pytest.fixture
def emitted_unfiltered() -> Any:
    buffer = io.StringIO()
    configure_logging(level="DEBUG", fmt="json", stream=buffer, redact=False)

    def emit(**fields: Any) -> str:
        get_logger("rag.test.unfiltered").info("chat turn", extra=log_extra(**fields))
        return buffer.getvalue().strip().splitlines()[-1]

    yield emit
    logging.getLogger().handlers.clear()


# -- the classifier ----------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "question",
        "query",
        "answer",
        "document_text",
        "chunk_text",
        "prompt",
        "completion",
        "content",
    ],
)
def test_content_field_names_are_recognised(name: str) -> None:
    assert is_content_field(name), f"{name!r} should be treated as user content"


@pytest.mark.parametrize(
    "name", ["request_id", "status_code", "duration_ms", "chat_model", "attempt", "score"]
)
def test_operational_field_names_are_allow_listed(name: str) -> None:
    assert is_safe_field(name), f"{name!r} is operational and should be allow-listed"


def test_unknown_field_names_are_not_allow_listed() -> None:
    """Default deny: an unrecognised field is summarised, not trusted.

    The opposite default -- letting unknown fields through because nobody objected -- is how
    redaction quietly stops working: someone adds ``user_query_text`` and it logs in full.
    """
    assert not is_safe_field("some_new_telemetry_field")
    assert not is_safe_field("document_body"), (
        "'document_body' is not on either list, so it must be summarised rather than trusted"
    )


# -- value redaction ---------------------------------------------------------


def test_redact_value_caps_recursion() -> None:
    """A self-referential structure must terminate rather than recurse forever."""
    nested: dict[str, Any] = {"a": 1}
    nested["self"] = nested
    redact_value(nested)  # must not raise


def test_redact_value_preserves_numbers() -> None:
    """Counts and scores survive; only text is summarised."""
    assert redact_value(7) == 7
    assert redact_value(1.5) == 1.5
    assert redact_value(True) is True
    assert redact_value(None) is None


def test_redact_value_summarises_collections() -> None:
    assert redact_value([1, 2, 3]) == "<list len=3>"
    assert redact_value("hello") == "<str len=5>"


def test_redact_mapping_three_way_outcome() -> None:
    result = redact_mapping(
        {
            "question": CONTENT_MARKER,
            "request_id": "req_1",
            "mystery": CONTENT_MARKER,
        }
    )
    assert result["question"] == REDACTED
    assert result["request_id"] == "req_1"
    assert result["mystery"] == f"<str len={len(CONTENT_MARKER)}>"


def test_filter_only_rewrites_extra_fields() -> None:
    """The filter targets ``extra_fields``, not arbitrary record attributes.

    Pinned because it is the whole reason :func:`log_extra` exists: rewriting arbitrary
    attributes would also mangle ``exc_info`` and friends.
    """
    record = logging.LogRecord(
        name="rag.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    record.__dict__["question"] = CONTENT_MARKER

    assert RedactionFilter().filter(record) is True
    assert record.__dict__["question"] == CONTENT_MARKER, (
        "the filter must not touch raw record attributes"
    )


def test_filter_rewrites_extra_fields() -> None:
    record = logging.LogRecord(
        name="rag.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    record.__dict__["extra_fields"] = {"question": CONTENT_MARKER}

    assert RedactionFilter().filter(record) is True
    assert record.extra_fields["question"] == REDACTED


def test_filter_is_idempotent() -> None:
    """Attaching the filter twice must not corrupt the record."""
    log_filter = RedactionFilter()
    record = logging.LogRecord(
        name="rag.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    record.__dict__["extra_fields"] = {"question": CONTENT_MARKER}

    for _ in range(3):
        assert log_filter.filter(record) is True
    assert record.extra_fields["question"] == REDACTED


def test_filter_tolerates_missing_extra_fields() -> None:
    """A logger attached before configuration must not explode at boot."""
    record = logging.LogRecord(
        name="rag.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="m",
        args=(),
        exc_info=None,
    )
    assert RedactionFilter().filter(record) is True
