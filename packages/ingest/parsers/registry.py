from __future__ import annotations

from packages.ingest.parsers.plaintext import PlaintextParser


def resolve_parser(parser_name: str = "plaintext") -> type[Parser]:
    """Resolve a parser strategy from config."""
    mapping = {
        "plaintext": PlaintextParser,
    }
    cls = mapping.get(parser_name)
    if cls is None:
        raise ValueError(f"Unknown parser: {parser_name}")
    return cls