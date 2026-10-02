from __future__ import annotations

from llm.ports import Embedder, Usage
from llm.ports.capabilities import ModelCapabilities as Capabilities
from core.clock import Clock, SystemClock


class HostedEmbedder:
    """Real embedder behind Embedder, with batch size, rate-limit handling, and reported dimensions."""

    def __init__(
        self,
        *,
        dimensions: int = 768,
        model_version: str = "hosted-embed-v1",
        batch_size: int = 64,
        rate_limit_per_min: int | None = None,
        capabilities: Capabilities | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._dimensions = dimensions
        self._model_version = model_version
        self._batch_size = max(1, batch_size)
        self._rate_limit_per_min = rate_limit_per_min
        self._capabilities = capabilities or Capabilities(
            streaming=False,
            json_mode=False,
            tool_calling=False,
            system_role=True,
            seeded_determinism=True,
            max_context_tokens=8192,
            max_output_tokens=4096,
        )
        self._clock = clock or SystemClock()
        self._last_usage = Usage(tokens_in=0, tokens_out=0)

    @property
    def name(self) -> str:
        return f"hosted-embed-{self._dimensions}d"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    @property
    def last_usage(self) -> Usage:
        return self._last_usage

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query text. In production, this would call the provider API."""
        # Simulate API call latency
        if self._latency_ms:
            from core.clock import sleep
            await sleep(self._latency_ms / 1000)
        
        # Placeholder: return dummy vector of correct dimension
        # Real implementation would call the embedding provider
        raise NotImplementedError(
            "Hosted embedder requires provider credentials and is available in phase 3+"
        )

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed multiple documents in batches."""
        if not texts:
            return []

        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batch_vectors = await self._embed_batch(batch)
            vectors.extend(batch_vectors)
        return vectors

    async def _embed_batch(self, batch: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts. Calls embed_query for each."""
        return [await self.embed_query(t) for t in batch]