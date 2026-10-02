from __future__ import annotations

import asyncio

from packages.ingest.models import Chunk, ParsedDocument, SourceRef
from packages.ingest.connectors.registry import resolve_connector
from packages.ingest.parsers.registry import resolve_parser
from packages.ingest.chunkers.registry import resolve_chunker
from packages.ingest.acl import derive_acl_tags
from packages.ingest.content_hash import content_hash


async def ingest_document(
    source_file: str,
    connector_name: str = "local_filesystem",
    parser_name: str = "plaintext",
    chunker_name: str = "fixed_window",
) -> tuple[list[Chunk], list[dict]]:
    """Full ingestion pipeline for a single document.

    Returns (chunks, metadata) where metadata includes the content hash
    and any derived information for downstream stages.
    """
    connector_class = resolve_connector(connector_name)
    connector = connector_class()  # instantiate
    chunks: list[Chunk] = []

    # 1. Fetch raw bytes
    raw_bytes = await connector.fetch(source_file)
    text = raw_bytes.decode("utf-8", errors="replace")

    # 2. Parse
    parser = resolve_parser(parser_name)()
    parsed = parser.parse(text, source_file)

    # 3. Derive ACL tags
    acl_tags = derive_acl_tags(parsed.get("metadata", {}))

    # 4. Chunk
    chunker = resolve_chunker(chunker_name)()
    chunk_output = chunker.chunk(text)

    # 5. Build Chunk objects
    chunks = []
    for i, chunk_text in enumerate(chunk_output["chunks"]):
        c_hash = content_hash(chunk_text, chunker_name, "fake-embed-v1")
        chunk = Chunk(
            text=chunk_text,
            token_count=chunk_output["token_counts"][i],
            char_start=chunk_output["char_starts"][i],
            char_end=chunk_output["char_ends"][i],
            hash=c_hash,
            acl_tags=acl_tags,
            heading_path=chunk_output.get("heading_paths", [i]),
        )
        chunks.append(chunk)

    metadata = {
        "source_file": source_file,
        "chunker_version": chunker_name,
        "parser_version": parser_name,
        "acl_tags": acl_tags,
    }

    return chunks, metadata


def run_ingest_document(
    source_file: str,
    connector_name: str = "local_filesystem",
    parser_name: str = "plaintext",
    chunker_name: str = "fixed_window",
) -> tuple[list[Chunk], list[dict]]:
    """Synchronous wrapper for ingest_document."""
    return asyncio.run(
        ingest_document(
            source_file,
            connector_name=connector_name,
            parser_name=parser_name,
            chunker_name=chunker_name,
        )
    )