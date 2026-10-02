"""Read a document or corpus and print its chunks with headings and token counts for human review."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.chunk_and_manifest import _parse_manifest_line


def inspect_manifest(manifest_path: Path = None, n: int = 20) -> None:
    """Inspect chunks from the manifest file."""
    if manifest_path is None:
        manifest_path = Path("chunks_manifest.txt")

    if not manifest_path.is_file():
        print(f"❌  Manifest not found: {manifest_path}")
        sys.exit(1)

    with manifest_path.open(encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]

    print(f"📄  Manifest has {len(lines)} chunks. Showing {min(n, len(lines))} randomly:")
    import random
    sample = random.sample(lines, min(n, len(lines)))
    for i, line in enumerate(sample, 1):
        chunk = _parse_manifest_line(line)
        print(f"\n--- Chunk {i} ---")
        print(f"  Hash: {chunk['hash'][:16]}...")
        print(f"  Text: {chunk['text'][:100]}...")
        print(f"  ACL tags: {chunk.get('acl_tags', [])}")
        print(f"  Char range: {chunk['char_start']}-{chunk['char_end']}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Inspect RAG chunks")
    parser.add_argument("--manifest", default="chunks_manifest.txt", help="Path to manifest file")
    parser.add_argument("--count", type=int, default=20, help="Number of chunks to show")
    args = parser.parse_args()
    inspect_manifest(Path(args.manifest), args.count)


if __name__ == "__main__":
    main()