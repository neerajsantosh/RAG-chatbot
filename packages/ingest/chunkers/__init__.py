from __future__ import annotations

from packages.ingest.chunkers.fixed_window import FixedWindowChunker
from packages.ingest.chunkers.registry import resolve_chunker

__all__ = ["FixedWindowChunker", "resolve_chunker", "Chunker"]


class Chunker:
    """Port definition for chunkers. Requires a ``version`` attribute."""
    version: str = "fixed_window_v1"