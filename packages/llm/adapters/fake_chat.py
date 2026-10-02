"""Deterministic offline chat model.

Returns a fixed, well-shaped response derived from its input. Two behaviours matter for
the phases that come after this one:

* **It emits citation markers.** Phase 5 tests citation verification against a model whose
  output looks like the real thing, including the case where a marker refers to a chunk
  that was never supplied.
* **It can be told to misbehave.** :meth:`FakeChatModel.misbehaving` produces dangling
  citations and uncited claims, which is how the citation-verification and repair tests get
  a genuinely bad answer without needing a real model to hallucinate on demand.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Sequence

from core.clock import Clock, SystemClock
from llm.ports import Completion, FinishReason, Message, ModelCapabilities, Usage
from llm.ports.capabilities import ModelCapabilities as Capabilities

__all__ = ["FakeChatModel", "Misbehaviour"]

_MARKER_PATTERN = re.compile(r"\[(\d+)\]")
"""Citation markers in the supplied context, matching the prompt contract in architecture §8.1."""


class Misbehaviour:
    """Named failure modes, so tests read as intent rather than as string literals."""

    NONE = "none"
    DANGLING_CITATION = "dangling_citation"
    UNCITED_CLAIM = "uncited_claim"
    REFUSAL = "refusal"


class FakeChatModel:
    """Deterministic stand-in for a hosted chat model."""

    __slots__ = (
        "_capabilities",
        "_chunk_size",
        "_clock",
        "_last_usage",
        "_latency_ms",
        "_name",
        "_version",
    )

    def __init__(
        self,
        *,
        name: str = "fake-chat",
        model_version: str = "fake-chat-v1",
        latency_ms: int = 0,
        chunk_size: int = 24,
        capabilities: Capabilities | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._name = name
        self._version = model_version
        self._latency_ms = max(0, latency_ms)
        self._chunk_size = max(1, chunk_size)
        self._clock = clock or SystemClock()
        self._last_usage = Usage(tokens_in=0, tokens_out=0)
        self._capabilities = capabilities or Capabilities(
            streaming=True,
            json_mode=False,
            tool_calling=False,
            system_role=True,
            seeded_determinism=True,
            max_context_tokens=32_000,
            max_output_tokens=4_096,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    @property
    def model_version(self) -> str:
        return self._version

    @property
    def last_usage(self) -> Usage:
        """Token usage from the most recent call.

        Only meaningful after consuming a :meth:`stream` iterator, since a generator has no
        way to hand a return value back to its caller.
        """
        return self._last_usage

    def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        stop: Sequence[str] | None = None,
        misbehaviour: str = Misbehaviour.NONE,
        **options: object,
    ) -> Iterator[str]:
        """Yield the canned response in fixed-size fragments.

        ``misbehaviour`` is a test-only hook on the adapter rather than an option the
        orchestrator knows about, so production code cannot select a bad behaviour by
        accident.
        """
        text, usage = self._render(messages, misbehaviour)
        if max_output_tokens is not None:
            text = text[: max(1, max_output_tokens) * 4]
            # Recomputed after truncation so cost reflects what was actually emitted.
            # Otherwise a capped request bills for output the caller never received.
            usage = self._usage(messages, text)

        if self._latency_ms:
            self._clock.sleep(self._latency_ms / 1000)

        # A generator cannot return a value, so usage is published as state. Callers that
        # bill a streamed response read it once the stream is exhausted (NFR-19).
        self._last_usage = usage

        for start in range(0, len(text), self._chunk_size):
            fragment = text[start : start + self._chunk_size]
            if stop:
                fragment = self._apply_stop(fragment, stop)
            yield fragment

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        stop: Sequence[str] | None = None,
        misbehaviour: str = Misbehaviour.NONE,
        **options: object,
    ) -> Completion:
        text, usage = self._render(messages, misbehaviour)
        if max_output_tokens is not None:
            text = text[: max(1, max_output_tokens) * 4]
            # Recomputed after truncation so cost reflects what was actually emitted.
            # Otherwise a capped request bills for output the caller never received (D10).
            usage = self._usage(messages, text)

        emitted = self._apply_stop(text, stop or ())
        if emitted is not text:
            usage = self._usage(messages, emitted)

        return Completion(
            text=emitted,
            usage=usage,
            model=self._name,
            model_version=self._version,
            finish_reason=self._finish_reason(text, max_output_tokens),
        )

    # -- internals ---------------------------------------------------------

    def _render(self, messages: Sequence[Message], misbehaviour: str) -> tuple[str, Usage]:
        prompt = "\n".join(message.content for message in messages)
        supplied = sorted({int(marker) for marker in _MARKER_PATTERN.findall(prompt)})

        if misbehaviour == Misbehaviour.REFUSAL:
            text = "I don't have enough in the indexed documents to answer this."
        elif misbehaviour == Misbehaviour.DANGLING_CITATION and supplied:
            text = f"According to the policy this is permitted [1][{supplied[-1] + 7}]."
        elif misbehaviour == Misbehaviour.UNCITED_CLAIM:
            text = "This is generally considered best practice across the industry."
        elif supplied:
            citations = ", ".join(f"[{index}]" for index in supplied[:2])
            text = f"Based on the indexed documents ({citations}), the answer is as follows."
        else:
            text = "The indexed documents do not contain an answer to this question."

        # Re-derive usage from the final text so cost is computed from actual output
        # rather than from a request-time estimate (D10).
        return text, self._usage(messages, text)

    @staticmethod
    def _usage(messages: Sequence[Message], output: str) -> Usage:
        prompt_chars = sum(len(message.content) for message in messages)
        # Four characters per token is the usual rule of thumb; good enough for a fake
        # whose only job is to produce a realistic shape.
        return Usage(
            tokens_in=max(1, prompt_chars // 4),
            tokens_out=max(0, len(output) // 4),
        )

    @staticmethod
    def _apply_stop(text: str, stop: Sequence[str]) -> str:
        for marker in stop:
            position = text.find(marker)
            if position >= 0:
                text = text[:position]
        return text

    @staticmethod
    def _finish_reason(text: str, max_output_tokens: int | None) -> FinishReason:
        if max_output_tokens is not None and len(text) >= max_output_tokens * 4:
            return "length"
        return "stop"

    def fingerprint(self, messages: Sequence[Message]) -> str:
        """A short stable digest of the prompt. Safe to log, unlike the prompt itself.

        Useful for asserting that a prompt changed when a template version changed, without
        recording the content.
        """
        joined = "\n".join(message.content for message in messages)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
