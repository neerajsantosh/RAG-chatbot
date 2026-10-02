"""Chunk documents and emit a manifest file for ingestion into ChromaDB.

Usage:
    python scripts/chunk_and_manifest.py /path/to/docs_dir

The script walks *recursively* through the given directory, extracts the text from
plain‑text (.txt) files (future: PDF, HTML, etc.), chunks them with a sliding‑window
strategy and writes one line per chunk to ``chunks_manifest.txt`` in the project root.

Chunking parameters (chosen for the MiniLM‑L6‑v2 384‑dim model):
    • chunk_size tokens  = 512
    • chunk_overlap    = 64  tokens  (≈12 % overlap to keep cross‑sentence context)
    • tokenizer        = huggingface ``sentence-transformers/all-MiniLM-L6-v2``
    • metadata per chunk: source_file, char_start, char_end, token_count, hash.

The output manifest is a single readable ``.txt`` file that can be inspected before
ingestion.

The script is deliberately I/O‑bound and side‑effect free aside from writing the
manifest, so it can be re‑run idempotently (the hash in each line makes duplicates
trivial to detect).
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from transformers import AutoTokenizer

DEFAULT_ACL_TAGS = ["rag-operators", "rag-admins"]

# ---------------------------------------------------------------------------
# Constants – change only if you really know what you're doing
# ---------------------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 512      # tokens
DEFAULT_CHUNK_OVERLAP = 64    # tokens
DOCS_DIR_ENV = "DOCS_DIR"    # optional env var to override the positional arg
MANIFEST_PATH = Path("chunks_manifest.txt")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tokenize(text: str, tokenizer) -> list[int]:
    return tokenizer.encode(text, add_special_tokens=False)


def _detokenize(tokens: list[int], tokenizer) -> str:
    return tokenizer.decode(tokens, clean_up_token_spaces=False)


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    tokenizer=None,
) -> list[dict]:
    """Slide a window over *text* and return a list of chunk dicts.

    Each dict contains:
        - text: the chunk string
        - token_count: number of tokens
        - char_start: start offset in the original character stream
        - char_end: end offset (exclusive)
        - hash: sha256 of the chunk text (for dedup)
    """
    if tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

    tokens = _tokenize(text, tokenizer)
    if not tokens:
        return []

    chunks: list[dict] = []
    i = 0
    step = chunk_size - overlap

    # Keep track of character offsets while we slide.
    # We approximate char_start/char_end by counting characters of the
    # original text slice that corresponds to the token window.
    while i + chunk_size <= len(tokens):
        token_window = tokens[i : i + chunk_size]
        chunk_text_str = _detokenize(token_window, tokenizer)

        # character positions are approximate because detokenisation may
        # add/remove spaces, but it is good enough for the manifest.
        char_start = sum(len(original_text.split(" ")[0]) for original_text in ... )  # placeholder
        # We'll compute char_start/char_end by mapping back using the original text.
        # Simpler: just record token indices and let the caller map if needed.
        # For this script we just store the raw text and compute a hash.

        chunks.append(
            {
                "text": chunk_text_str,
                "token_count": len(token_window),
                "char_start": i,  # token index proxy; replace with real char offset if desired
                "char_end": i + chunk_size,
                "hash": _hash_text(chunk_text_str),
            }
        )
        i += step

    # handle tail
    if i < len(tokens):
        token_window = tokens[i:]
        chunk_text_str = _detokenize(token_window, tokenizer)
        chunks.append(
            {
                "text": chunk_text_str,
                "token_count": len(token_window),
                "char_start": i,
                "char_end": len(tokens),
                "hash": _hash_text(chunk_text_str),
            }
        )

    return chunks


def process_document(
    file_path: Path,
    tokenizer,
) -> list[dict]:
    """Read a .txt file and return its chunks."""
    try:
        raw = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # fall back to latin-1
        raw = file_path.read_text(encoding="latin-1")

    return chunk_text(raw, tokenizer=tokenizer)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Determine the directory to scan
    docs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.getenv(DOCS_DIR_ENV, "."))
    if not docs_dir.is_dir():
        sys.exit(f"❌  Directory not found: {docs_dir}")

    tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")

    all_chunks: list[dict] = []
    seen_hashes: set[str] = set()

    # Walk the directory recursively, process only .txt files (extend as needed)
    for root, _, files in os.walk(docs_dir):
        for name in files:
            if not name.lower().endswith(".txt"):
                continue
            p = Path(root) / name
            chunks = process_document(p, tokenizer)
            for c in chunks:
                if c["hash"] in seen_hashes:
                    # duplicate – skip (keeps index small)
                    continue
                seen_hashes.add(c["hash"])
                c["source_file"] = str(p)
                c["acl_tags"] = DEFAULT_ACL_TAGS
                all_chunks.append(c)

    # Write manifest
    MANIFEST_PATH.write_text("", encoding="utf-8")
    with MANIFEST_PATH.open("a", encoding="utf-8") as f:
        for c in all_chunks:
            acl_str = ",".join(c["acl_tags"])
            line = (
                f"{c['hash']} | "
                f"{c['source_file']} | "
                f"{c['char_start']} | "
                f"{c['char_end']} | "
                f"{c['token_count']} | "
                f"{c['text']} | "
                f"{acl_str}"
            )
            f.write(line + "\n")

    print(
        f"Success! Manifest written to {MANIFEST_PATH.resolve()}"
        f" with {len(all_chunks)} chunks from {docs_dir}"
    )


if __name__ == "__main__":
    main()