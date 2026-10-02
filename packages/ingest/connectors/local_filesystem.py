from __future__ import annotations

import asyncio
from pathlib import Path


class Connector:
    """Base class for document connectors."""

    async def enumerate_sources(self) -> list[str]:
        raise NotImplementedError

    async def fetch(self, source_id: str) -> bytes:
        raise NotImplementedError


class LocalFilesystemConnector(Connector):
    """Connector for a directory of documents."""

    def __init__(self, directory: str = ".") -> None:
        self.directory = Path(directory)

    async def enumerate_sources(self) -> list[str]:
        """Return list of source file paths in the configured directory."""
        files: list[str] = []
        for p in self.directory.rglob("*.txt"):
            files.append(str(p.resolve()))
        return files

    async def fetch(self, source_id: str) -> bytes:
        """Fetch raw bytes for a given source id."""
        return Path(source_id).read_bytes()