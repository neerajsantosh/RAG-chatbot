"""Export ChromaDB chunk embeddings to a plain‑text file.

Result: embeddings.txt  (one line per chunk)
format: chunk_id | chunk_text | token1 token2 ... token384
"""
from __future__ import annotations

import pathlib

from sentence_transformers import SentenceTransformer

from packages.vector.chroma_store import ChromaStore


def main() -> None:
    chroma = ChromaStore()
    coll = chroma._ensure()

    # collect all chunk ids stored in the collection
    full = coll.get()  # type: ignore
    all_ids: list[str] = full["ids"]  # type: ignore

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    out_path = pathlib.Path("embeddings.txt")
    with out_path.open("w", encoding="utf-8") as out:
        for chunk_id in all_ids:
            # fetch the stored document text and its vector
            data = coll.get(ids=[chunk_id], include=["documents", "embeddings"])  # type: ignore
            text: str = data["documents"][0]
            vec = data["embeddings"][0]  # list of 384 floats
            # format the vector as space‑separated numbers with 6 decimal places
            vec_str = " ".join(f"{v:.6f}" for v in vec)
            # escape any pipe in the text so the line stays parseable
            text_escaped = text.replace("|", r"\|")
            out.write(f"{chunk_id} | {text_escaped} | {vec_str}\n")

    print("Embeddings written to " + str(out_path.resolve()))


if __name__ == "__main__":
    main()