from __future__ import annotations

from packages.ingest.chunkers.fixed_window import FixedWindowChunker


def resolve_chunker(chunker_name: str = "fixed_window") -> type[Chunker]:
    """Resolve a chunker strategy from config."""
    mapping = {
        "fixed_window": FixedWindowChunker,
    }
    cls = mapping.get(chunker_name)
    if cls is None:
        raise ValueError(f"Unknown chunker: {chunker_name}")
    return cls