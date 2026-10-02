"""Deterministic offline embeddings.

Vectors are derived from ``sha256`` of hashed token bags, so they are stable across
processes and machines -- unlike ``hash()``, which is randomised per process and would
make every test that depends on embeddings fail on a second run.

The vectors are not semantically meaningful, and are not meant to be. What they
deliberately do preserve is the property retrieval depends on: two similar texts produce
similar vectors, because shared tokens contribute to shared dimensions. That is enough for
phase 3's plumbing tests. Recall measured against these vectors means nothing, which is
why the golden dataset and the real embedder arrive together in phase 3.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Final

from core.errors import ValidationFailed

__all__ = ["FakeEmbedder", "tokenize"]

_TOKEN_PATTERN: Final = re.compile(r"[a-z0-9]+")
"""Lowercased alphanumeric tokens. Deliberately crude and deliberately stable."""


def tokenize(text: str) -> list[str]:
    """Split text into lowercase alphanumeric tokens."""
    return _TOKEN_PATTERN.findall(text.lower())


class FakeEmbedder:
    """A hashed bag-of-tokens embedder. Same input, same vector, every time."""

    __slots__ = ("_batch_size", "_dimensions", "_model_version", "_name")

    def __init__(
        self,
        *,
        dimensions: int = 1024,
        model_version: str = "fake-embed-v1",
        batch_size: int = 64,
        name: str = "fake",
    ) -> None:
        if dimensions < 8:
            raise ValueError(f"dimensions must be at least 8, got {dimensions}")
        self._name = name
        self._dimensions = dimensions
        self._model_version = model_version
        self._batch_size = max(1, batch_size)

    @property
    def name(self) -> str:
        return self._name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def batch_size(self) -> int:
        return self._batch_size

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        """Hash each token into a fixed set of dimensions, then L2-normalise.

        Normalisation means every vector has unit length, so cosine similarity is a plain
        dot product and a later phase cannot accidentally compare unnormalised vectors.
        """
        vector = [0.0] * self._dimensions
        tokens = tokenize(text)

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # Use the first 8 bytes to pick a bucket, the next 4 for a signed weight.
            bucket = int.from_bytes(digest[:8], "big") % self._dimensions
            sign = 1.0 if digest[8] % 2 == 0 else -1.0
            vector[bucket] += sign

        # An empty or symbol-only text yields a zero vector. That is a real input (a
        # document that is an image, a table with no prose) and returning a unit vector
        # from noise would be a lie that surfaces as confident nonsense in retrieval.
        magnitude = math.sqrt(sum(component * component for component in vector))
        if magnitude == 0.0:
            return vector
        return [component / magnitude for component in vector]

    def validate_batch(self, vectors: Sequence[Sequence[float]]) -> None:
        """Assert every vector has exactly ``dimensions`` components.

        Called before writing to the index so a dimension mismatch fails loudly instead of
        silently writing unusable vectors (architecture §9.4).
        """
        for position, vector in enumerate(vectors):
            if len(vector) != self._dimensions:
                raise ValidationFailed(
                    f"embedding {position} has width {len(vector)}, expected {self._dimensions}",
                    code="embedding_dimension_mismatch",
                    details={"position": position, "actual": len(vector)},
                )
