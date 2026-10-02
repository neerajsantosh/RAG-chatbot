"""Persistent ChromaDB wrapper for the RAG chatbot.

Responsibilities
----------------
* Initialise a ``chroma`` ``PersistentClient`` pointing at ``./chroma_db`` (on‑disk).
* Provide a ``add_chunks_from_manifest`` helper that reads the ``chunks_manifest.txt``
  format produced by ``scripts/chunk_and_manifest.py`` and creates/updates a
  collection called ``legal_docs``.
* Provide a ``query`` method that returns the top‑k most similar chunk texts and
  their metadata for a given query string, optionally filtered by user ACL groups.
* The collection stores the embedding (384‑dim), the chunk text, and metadata
  fields (source file, char range, token count, hash, acl_tags).

The module is deliberately tiny; all heavy lifting (tokenising, embedding) is
delegated to the ``sentence‑transformers`` model that the ingestion pipeline already
uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import chromadb

# ---------------------------------------------------------------------------
# Constants – keep them aligned with the embedding model dimensions
# ---------------------------------------------------------------------------
CHROMA_PERSIST_DIR = Path("./chroma_db")
COLLECTION_NAME = "legal_docs"
EMBEDDING_DIM = 384  # all-MiniLM-L6‑v2
DEFAULT_TOP_K = 6

MANIFEST_DEFAULT = Path("chunks_manifest.txt")

# Default ACL tags that will be assigned to chunks if none are specified in the manifest.
DEFAULT_ACL_TAGS = ["rag-operators", "rag-admins"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_line(line: str) -> str:
    """Hash the whole manifest line so we can detect duplicates later."""
    return __import__("hashlib").sha256(line.encode("utf-8")).hexdigest()


def _parse_manifest_line(line: str) -> dict:
    """Turn a manifest line produced by ``chunk_and_manifest.py`` into a dict.

    Expected format (pipe‑separated):
        hash | source_file | char_start | char_end | token_count | text | acl_tags
    The ``acl_tags`` field is a comma‑separated list of group names; if it is
    omitted the ``DEFAULT_ACL_TAGS`` are used.
    """
    parts = [p.strip() for p in line.split(" | ")]
    if len(parts) < 6 or len(parts) > 7:
        raise ValueError(f"Malformed manifest line: {line!r}")

    # guaranteed at least 6 fields; a 7th field optional for acl_tags
    chunk: dict = {
        "hash": parts[0],
        "source_file": parts[1],
        "char_start": int(parts[2]),
        "char_end": int(parts[3]),
        "token_count": int(parts[4]),
        "text": parts[5],
    }

    # acl_tags may be present (parts[6]) or default
    if len(parts) == 7 and parts[6]:
        # comma‑separated list, strip whitespace around each tag
        acl_tags = [t.strip() for t in parts[6].split(",") if t.strip()]
    else:
        acl_tags = list(DEFAULT_ACL_TAGS)  # type: ignore

    chunk["acl_tags"] = acl_tags
    return chunk


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ChromaStore:
    """Thin wrapper around a Chroma ``Collection``.

    The constructor lazily creates the client + collection the first time it is
    used, so importing the class does not I/O‑block.
    """

    def __init__(self, user_groups: list[str] | None = None) -> None:
        self._client: chromadb.PersistentClient | None = None
        self._collection = None
        # Store the user groups for ACL‑aware querying; if None the query will
        # return everything (used by tests/CI).
        self._user_groups: list[str] = user_groups if user_groups is not None else []

    # ------------------------------------------------------------------
    # Internal lazy init
    # ------------------------------------------------------------------
    def _ensure(self) -> chromadb.Collection:
        if self._collection is not None:
            return self._collection
        CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"dimension": EMBEDDING_DIM, "hnsw:space": "cosine"},
        )
        return self._collection

    # ------------------------------------------------------------------
    # Set user groups after construction
    # ------------------------------------------------------------------
    def set_user_groups(self, groups: list[str]) -> None:
        """Replace the ACL user groups for subsequent queries."""
        self._user_groups = groups

    # ------------------------------------------------------------------
    # Ingest from the manifest
    # ------------------------------------------------------------------
    def add_chunks_from_manifest(self, manifest_path: Path | str = MANIFEST_DEFAULT) -> int:
        """Read ``manifest_path`` and upsert each chunk into the collection.

        Returns the number of chunks added/updated.
        """
        coll = self._ensure()
        added = 0
        manifest_path = Path(manifest_path)
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with manifest_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = _parse_manifest_line(line)
                except ValueError as exc:
                    print(f"⚠️  Skipping malformed line: {exc}")
                    continue

                # Compute embedding on‑the‑fly (384‑dim)
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                embedding = model.encode(chunk["text"]).tolist()

                # Use the hash as the Chroma id – guarantees idempotency
                chunk_id = chunk["hash"]

                # Metadata we keep for later query‑time filtering
                metadata = {
                    "source_file": chunk["source_file"],
                    "char_start": chunk["char_start"],
                    "char_end": chunk["char_end"],
                    "token_count": chunk["token_count"],
                    "hash": chunk["hash"],
                    "acl_tags": chunk["acl_tags"],
                }

                # Upsert – if an id already exists the values are replaced
                coll.upsert(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk["text"]],
                    metadatas=[metadata],
                )
                added += 1

        return added

    # ------------------------------------------------------------------
    # Query with optional ACL filtering
    # ------------------------------------------------------------------
    def query(self, text: str, k: int = DEFAULT_TOP_K) -> list[dict]:
        """Return the top‑k most similar chunks for *text*.

        If ``self._user_groups`` is non‑empty, only chunks whose
        ``metadata["acl_tags"]`` intersects with the user groups are returned.
        The result list preserves the original similarity order after filtering.

        Each result dict contains:
            - ``text``: the chunk content
            - ``metadata``: the stored metadata (source_file, char range, etc.)
            - ``distance``: cosine distance (lower = more similar)
        """
        coll = self._ensure()
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        query_emb = model.encode(text).tolist()

        results = coll.query(
            query_embeddings=[query_emb],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

        output: list[dict] = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        # If the user has specified ACL groups, filter the results.
        if self._user_groups:
            filtered: list[dict] = []
            for d, m, dist in zip(docs, metas, dists):
                chunk_tags: list[str] = m.get("acl_tags", [])
                # Keep the chunk if any of its tags overlap with the user groups.
                if set(chunk_tags) & set(self._user_groups):
                    filtered.append(
                        {
                            "text": d or "",
                            "metadata": m or {},
                            "distance": dist,
                        }
                    )
            output = filtered
        else:
            # No ACL restriction – return everything retrieved.
            for d, m, dist in zip(docs, metas, dists):
                output.append(
                    {
                        "text": d or "",
                        "metadata": m or {},
                        "distance": dist,
                    }
                )
        return output

    # ------------------------------------------------------------------
    # Helper to delete the whole collection (useful for tests)
    # ------------------------------------------------------------------
    def reset(self) -> None:
        if self._client is not None:
            self._client.delete_collection(name=COLLECTION_NAME)
        self._collection = None