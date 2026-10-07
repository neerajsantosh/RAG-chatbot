#!/usr/bin/env python
"""Phase 3 – Embedding and Vector Store.

Reads the chunks produced by Phase 2 (`data/chunks.txt`), embeds each chunk
with `sentence-transformers/all-MiniLM-L6-v2` (384‑dim) and stores them in
a persisted ChromaDB instance (`chroma_db/`).

The script is idempotent: if the collection already contains the same
chunks (by ID) it skips adding them again.
"""

import os
import json
import sqlite3
from typing import List, Dict

from sentence_transformers import SentenceTransformer
import chromadb
from dotenv import load_dotenv

load_dotenv()
# GROQ_API_KEY is not needed for this phase but kept for consistency
# GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CHUNK_FILE = os.path.join("data", "chunks.txt")
CHROMA_PATH = os.path.join("chroma_db")
COLLECTION_NAME = "hdfc_funds"


def parse_chunks(filepath: str) -> List[Dict]:
    """Parse chunks.txt into a list of dicts with id, text, metadata."""
    chunks = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            # Expected format: CHUNK_ID|SCHEME|CATEGORY|URL|HEADING|TEXT
            # The TEXT may contain '|' characters, so we treat the last part as text
            # and re‑join the middle fields if needed.
            if len(parts) < 6:
                # malformed line – skip
                continue
            chunk_id = parts[0]
            scheme = parts[1] if len(parts) > 1 else ""
            category = parts[2] if len(parts) > 2 else ""
            url = parts[3] if len(parts) > 3 else ""
            heading = parts[4] if len(parts) > 4 else ""
            # re‑join any remaining parts as the text (in case it contains '|')
            text = "|".join(parts[5:]) if len(parts) > 5 else parts[5]
            metadata = {
                "scheme_name": scheme,
                "category": category,
                "url": url,
                "heading": heading,
            }
            chunks.append({"id": chunk_id, "text": text, "metadata": metadata})
    return chunks


def get_existing_ids(client: chromadb.PersistentClient, collection_name: str) -> set:
    """Return a set of chunk IDs already stored in the collection."""
    try:
        coll = client.get_collection(collection_name)
        # chroma db 1.5+ stores ids; we can fetch all ids via get with limit
        # Use a large limit to retrieve all
        all_ids = coll.get(include=[])["ids"]
        return set(all_ids)
    except Exception:
        # collection might be empty or not exist yet
        return set()


def main():
    # Parse chunks from the txt file
    chunks = parse_chunks(CHUNK_FILE)
    print(f"Parsed {len(chunks)} chunks from {CHUNK_FILE}")

    # Initialise the MiniLM-L6-v2 embedding model (local, no API key)
    print("Loading embedding model 'sentence-transformers/all-MiniLM-L6-v2' ...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    # Initialise ChromaDB client (persistent)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # Get or create the collection
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    # Determine which IDs are already present
    existing_ids = get_existing_ids(client, COLLECTION_NAME)
    print(f"Existing IDs in ChromaDB: {len(existing_ids)}")

    # Filter out chunks that are already stored
    to_embed = [c for c in chunks if c["id"] not in existing_ids]
    print(f"Chunks to embed: {len(to_embed)}")

    if not to_embed:
        print("All chunks are already embedded. Nothing to do.")
        return

    # Embed the new chunks
    texts = [c["text"] for c in to_embed]
    print("Generating embeddings (this may take a moment)...")
    embeddings = model.encode(texts, show_progress_bar=True)
    # Convert to list of lists for ChromaDB
    embeddings_lst = embeddings.tolist()

    # Prepare payloads
    ids = [c["id"] for c in to_embed]
    metadatas = [c["metadata"] for c in to_embed]

    # Add to ChromaDB
    print("Adding embeddings to ChromaDB...")
    collection.add(
        ids=ids,
        embeddings=embeddings_lst,
        metadatas=metadatas,
        documents=texts,  # store the raw text as document for retrieval
    )

    # Persist (ChromaDB writes to disk automatically, but we call ensure_persist)
    collection.persist()
    print(f"Successfully added {len(to_embed)} chunks to ChromaDB at '{CHROMA_PATH}'.")
    print("Phase 3 complete.")


if __name__ == "__main__":
    main()