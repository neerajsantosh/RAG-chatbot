"""The three model ports.

These protocols are the entire surface the rest of the application sees. Two design
constraints are enforced by the shapes chosen here:

* **Token counts travel with every result.** ``Completion`` and ``embed_documents``
  return usage, because NFR-19 requires cost computed from actual tokens per answer --
  a design that only returns text forces cost to be estimated in aggregate afterwards.
* **Nothing exposes a tool surface.** ``ChatModel.complete`` accepts messages and
  options, and no tools, functions or callbacks. This is architecture §8.3's strongest
  control against prompt injection, and encoding it in the type means a caller cannot
  reach a tool even by mistake.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from llm.ports.capabilities import ModelCapabilities

__all__ = [
    "ChatModel",
    "Completion",
    "Embedder",
    "FinishReason",
    "Message",
    "Reranker",
    "Role",
    "Usage",
]

Role = Literal["system", "user", "assistant"]
FinishReason = Literal["stop", "length", "content_filter", "error"]


@dataclass(frozen=True, slots=True)
class Message:
    """One turn in a chat exchange."""

    role: Role
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class Usage:
    """Actual token counts for one call.

    ``tokens_out`` on a streamed call is only final once the stream is exhausted; the
    orchestrator must read it after the last token, not at the start.
    """

    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.tokens_in + other.tokens_in, self.tokens_out + other.tokens_out)

    def to_dict(self) -> dict[str, int]:
        return {"tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "total": self.total}


@dataclass(frozen=True, slots=True)
class Completion:
    """A finished, non-streamed generation."""

    text: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    model_version: str = ""
    finish_reason: FinishReason = "stop"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "usage": self.usage.to_dict(),
            "model": self.model,
            "model_version": self.model_version,
            "finish_reason": self.finish_reason,
        }


@runtime_checkable
class ChatModel(Protocol):
    """Text generation."""

    @property
    def name(self) -> str:
        """Configured model name, as recorded on every trace (NFR-13)."""
        ...

    @property
    def capabilities(self) -> ModelCapabilities:
        ...

    def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        stop: Sequence[str] | None = None,
        **options: Any,
    ) -> Iterator[str]:
        """Yield text fragments in order.

        Note there is no ``tools`` parameter. Tool calling is a PRD §3 non-goal and its
        absence here is a safety property, not an oversight.
        """
        ...

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        stop: Sequence[str] | None = None,
        **options: Any,
    ) -> Completion:
        """Generate a full response with usage accounted for."""
        ...


@runtime_checkable
class Embedder(Protocol):
    """Text to vector."""

    @property
    def name(self) -> str:
        ...

    @property
    def dimensions(self) -> int:
        """Vector width. Must match the stored column width exactly (architecture §9.4)."""
        ...

    @property
    def model_version(self) -> str:
        """Part of ``content_hash``; changing it forces re-embedding (FR-4)."""
        ...

    @property
    def batch_size(self) -> int:
        ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


@runtime_checkable
class Reranker(Protocol):
    """Score a query against passages jointly."""

    @property
    def name(self) -> str:
        ...

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """Return one score per passage, same order. Higher is more relevant."""
        ...

    def top_n(self, query: str, passages: Sequence[str], n: int) -> list[tuple[int, float]]:
        """Return the ``n`` best ``(index, score)`` pairs, highest score first."""
        ...
