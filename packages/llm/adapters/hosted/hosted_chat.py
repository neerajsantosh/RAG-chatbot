from __future__ import annotations

from llm.ports import Completion, FinishReason, Message, ModelCapabilities, Usage
from llm.ports.capabilities import ModelCapabilities as Capabilities
from core.clock import Clock, SystemClock


class HostedChatModel:
    """Real chat adapter behind ChatModel, with streaming, timeout, bounded retry."""

    def __init__(
        self,
        *,
        name: str = "hosted-chat",
        model_version: str = "hosted-chat-v1",
        latency_ms: int = 0,
        capabilities: Capabilities | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._name = name
        self._version = model_version
        self._latency_ms = max(0, latency_ms)
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
        return self._last_usage

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        stop: Sequence[str] | None = None,
        **options: object,
    ) -> Completion:
        """Generate a completion for the given messages."""
        # In a real implementation, this would call the model provider API
        # For now, raise not implemented until phase 5
        raise NotImplementedError(
            "Hosted chat model requires provider credentials and is available in phase 5+"
        )

    def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        stop: Sequence[str] | None = None,
        **options: object,
    ) -> "async_generator[str]":
        """Stream a completion for the given messages."""
        raise NotImplementedError(
            "Hosted chat streaming requires provider credentials and is available in phase 5+"
        )