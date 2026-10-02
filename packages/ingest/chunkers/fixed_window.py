from __future__ import annotations

from typing import Final
from packages.ingest.models import Chunk
from packages.ingest.content_hash import content_hash


DEFAULT_CHUNK_SIZE: Final = 512
DEFAULT_CHUNK_OVERLAP: Final = 64


class FixedWindowChunker:
    """Overlapping fixed-size windows for flat text."""

    version: str = "fixed_window_v1"

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.step = chunk_size - overlap

    def chunk(self, text: str, model_version: str = "fake-embed-v1") -> dict:
        """Slide a window over text and return chunk information."""
        chunks: list[str] = []
        token_counts: list[int] = []
        char_starts: list[int] = []
        char_ends: list[int] = []
        heading_paths: list[list[int]] = []

        # Use a simple token-based approximation for chunking
        # In a full implementation, would use a proper tokenizer
        tokens = text.split()
        if not tokens:
            return {
                "chunks": [],
                "token_counts": [],
                "char_starts": [],
                "char_ends": [],
                "heading_paths": [],
            }

        i = 0
        while i + self.chunk_size <= len(tokens):
            window = tokens[i : i + self.chunk_size]
            chunk_text = " ".join(window)
            c_hash = content_hash(chunk_text, self.version, model_version)
            chunks.append(chunk_text)
            token_counts.append(len(window))
            char_starts.append(i)
            char_ends.append(i + self.chunk_size)
            heading_paths.append([])
            i += self.step

        # handle tail
        if i < len(tokens):
            window = tokens[i:]
            chunk_text = " ".join(window)
            c_hash = content_hash(chunk_text, self.version, model_version)
            chunks.append(chunk_text)
            token_counts.append(len(window))
            char_starts.append(i)
            char_ends.append(len(tokens))
            heading_paths.append([])

        return {
            "chunks": chunks,
            "token_counts": token_counts,
            "char_starts": char_starts,
            "char_ends": char_ends,
            "heading_paths": heading_paths,
        }