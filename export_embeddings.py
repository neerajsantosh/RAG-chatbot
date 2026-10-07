#!/usr/bin/env python
"""Export chunk embeddings from ChromaDB to embedding.txt."""

import os
import chromadb
from sentence_transformers import SentenceTransformer

# ChromaDB path
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
# Output file
OUT_PATH = os.path.join(os.path.dirname(__file__), "embedding.txt")

def main():
    # Initialise ChromaDB client (persistent)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection("hdfc_funds")

    # Retrieve all IDs and their embeddings
    # include='embeddings' returns ids and embeddings together
    result = collection.get(include=["embeddings"])
    ids = result["ids"]           # list of chunk IDs (strings)
    embeddings = result["embeddings"]  # list of lists (each 384-dim)

    # Write to embedding.txt
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for chunk_id, vec in zip(ids, embeddings):
            # Format: chunk_id, v1, v2, ..., v384
            parts = [chunk_id] + [str(v) for v in vec]
            f.write(",".join(parts) + "\n")

    print(f"Wrote {len(ids)} embeddings to {OUT_PATH}")

if __name__ == "__main__":
    main()