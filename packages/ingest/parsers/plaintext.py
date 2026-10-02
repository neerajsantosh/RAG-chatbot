from __future__ import annotations

import re
from packages.ingest.models import ParsedDocument, DocumentSection, SourceRef


class PlaintextParser:
    """Parser for plain text documents: encoding detection, paragraph boundaries."""

    def parse(self, text: str, source_file: str) -> dict:
        """Split text into paragraphs and return a ParsedDocument."""
        # Simple paragraph split on double newlines
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        sections: list[DocumentSection] = []
        char_pos = 0
        for para in paragraphs:
            para_start = text.index(para, char_pos) if char_pos > 0 else text.index(para)
            para_end = para_start + len(para)
            sections.append(
                DocumentSection(
                    title="",
                    text=para,
                    char_start=para_start,
                    char_end=para_end,
                )
            )
            char_pos = para_end

        return {
            "document": ParsedDocument(
                source=SourceRef(source_file=source_file),
                sections=sections,
            )
        }