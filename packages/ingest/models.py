from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class SourceRef:
    source_file: str
    hash: str = field(default="")
    acl_tags: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    source: SourceRef
    sections: list[dict] = field(default_factory=list)


@dataclass
class DocumentSection:
    title: str
    text: str
    char_start: int
    char_end: int


@dataclass
class Chunk:
    text: str
    token_count: int
    char_start: int
    char_end: int
    hash: str
    acl_tags: list[str]
    heading_path: list[str] | None = None