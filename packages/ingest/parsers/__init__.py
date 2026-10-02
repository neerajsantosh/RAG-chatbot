from __future__ import annotations

from packages.ingest.parsers.plaintext import PlaintextParser
from packages.ingest.parsers.registry import resolve_parser

__all__ = ["PlaintextParser", "resolve_parser", "Parser"]


class Parser:
    """Port definition for document parsers."""

    def parse(self, text: str, source_file: str) -> dict: ...