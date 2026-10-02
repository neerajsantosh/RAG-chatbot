from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class Hit:
    """A single retrieval result with score and metadata."""
    chunk_id: str
    score: float
    text: str
    metadata: dict = field(default_factory=dict)
    rank: int = 0


@dataclass
class RankedList:
    """Ranked list of retrieval hits."""
    hits: list[Hit] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.hits)

    def __getitem__(self, idx: int) -> Hit:
        return self.hits[idx]


@dataclass
class RetrievedContext:
    """Context returned from retrieval, containing ranked hits and provenance."""
    ranked: RankedList
    query: str
    total_chunks_searched: int = 0