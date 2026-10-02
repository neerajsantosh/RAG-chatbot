"""CLI smoke path: ask a RAG question without the UI.

Usage:
    python tools/ask.py "What is our policy on annual leave carry-over?"

Prints the answer, which chunks were retrieved, and citation metadata.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

from packages.pipeline.orchestrator import answer_question


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/ask.py \"your question here\"")
        sys.exit(1)

    question: str = " ".join(sys.argv[1:])

    print(f"❓  Question: {question}")
    print("\n🔎  Retrieving chunks and generating answer...\n")

    result = answer_question(question)

    # Print the answer
    print("💡  Answer:")
    print(result["answer"])
    print()

    # Print retrieved chunks with metadata
    print(f"📄  Retrieved {len(result['chunks'])} chunk(s):")
    for i, chunk in enumerate(result["chunks"], start=1):
        text_preview = chunk.get("text", "")[:100].replace("\n", " ")
        meta = chunk.get("metadata", {})
        source = meta.get("source_file", "unknown")
        tags = meta.get("acl_tags", [])
        print(f"   [{i}] {source} (acl: {tags}) — {text_preview}...")

    print()

    # Print citations
    print("🔗  Citations:")
    if result["citations"]:
        for c in result["citations"]:
            print(f"   [{c['index']}] source={c['source_file']} "
                  f"({c['text_start']}-{c['text_end']})")
    else:
        print("   (no numbered citations in answer)")


if __name__ == "__main__":
    main()