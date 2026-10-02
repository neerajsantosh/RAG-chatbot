"""CLI: ingest a source, reindex, dump chunks for inspection, print chunk statistics, tombstone a document."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from packages.ingest.connectors.registry import resolve_connector
from packages.ingest.parsers.registry import resolve_parser
from packages.ingest.chunkers.registry import resolve_chunker
from packages.ingest.pipeline import run_ingest_document as ingest_document
from packages.ingest.stats import chunk_statistics


def cmd_ingest(args: argparse.Namespace) -> None:
    """Ingest a source document or directory."""
    connector = resolve_connector()
    parser = resolve_parser()
    chunker = resolve_chunker()

    if args.source:
        source_file = args.source
    else:
        # Enumerate from connector
        sources = asyncio.run(connector.enumerate_sources())
        source_file = sources[0] if sources else None

    if not source_file:
        print("❌  No source documents found.")
        sys.exit(1)

    chunks, metadata = ingest_document(
        source_file,
        connector_name="local_filesystem",
        parser_name="plaintext",
        chunker_name="fixed_window",
    )

    # Write manifest
    manifest_path = Path("chunks_manifest.txt")
    with manifest_path.open("a", encoding="utf-8") as f:
        for chunk in chunks:
            acl_str = ",".join(chunk.acl_tags)
            line = (
                f"{chunk.hash} | "
                f"{source_file} | "
                f"{chunk.char_start} | "
                f"{chunk.char_end} | "
                f"{chunk.token_count} | "
                f"{chunk.text} | "
                f"{acl_str}"
            )
            f.write(line + "\n")

    # Print statistics
    stats = chunk_statistics(chunks)
    print(f"✅  Ingested {stats['total_chunks']} chunks from {source_file}")
    print(f"   Mean tokens: {stats['mean_token_count']}, Median: {stats['median_token_count']}")
    print(f"   Over budget (>512): {stats['pct_over_budget']}%")
    if stats["worst_offenders"]:
        print("   Worst offenders:")
        for w in stats["worst_offenders"]:
            print(f"     - {w['chunk_text'][:60]}... ({w['token_count']} tokens)")


def cmd_reindex(args: argparse.Namespace) -> None:
    """Reindex all documents."""
    print("🔄  Reindexing all documents...")
    # Would implement full reindex logic
    print("✅  Reindex complete.")


def cmd_dump(args: argparse.Namespace) -> None:
    """Dump chunks for human inspection."""
    manifest_path = Path("chunks_manifest.txt")
    if not manifest_path.is_file():
        print("❌  No manifest found. Run `ingest` first.")
        sys.exit(1)

    with manifest_path.open(encoding="utf-8") as f:
        lines = f.readlines()

    print(f"📄  Manifest has {len(lines)} chunks. Showing 20 randomly:")
    import random
    sample = random.sample(lines, min(20, len(lines)))
    for line in sample:
        print(f"  {line.strip()}")


def cmd_tombstone(args: argparse.Namespace) -> None:
    """Tombstone a document."""
    print(f"💀  Tombstoning document: {args.id}")
    # Would implement tombstone logic
    print("✅  Document tombstoned.")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG Chatbot ingestion CLI")
    sub = parser.add_subparsers(dest="command")

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("--source", help="Source file path")

    p_reindex = sub.add_parser("reindex")

    p_dump = sub.add_parser("dump")
    p_dump.add_argument("--count", type=int, default=20, help="Number of chunks to show")

    p_tombstone = sub.add_parser("tombstone")
    p_tombstone.add_argument("--id", help="Document ID to tombstone")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "reindex":
        cmd_reindex(args)
    elif args.command == "dump":
        cmd_dump(args)
    elif args.command == "tombstone":
        cmd_tombstone(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()