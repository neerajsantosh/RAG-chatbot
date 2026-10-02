"""Reranker for retrieval results.

Provides a CrossEncoder‑based re‑ranking of candidate chunks.
If the CrossEncoder model cannot be loaded, a simple fallback sorts by
chunk length (longer chunks are assumed to contain more information).
"""

from __future__ import annotations

from typing import List, Dict

try:
    from sentence_transformers import CrossEncoder
    _CE_AVAILABLE = True
except Exception:  # pragma: no cover
    _CE_AVAILABLE = False


def rerank_chunks(query: str, chunks: List[Dict], top_n: int = 6) -> List[Dict]:
    """Re‑rank *chunks* for the given *query* and return the top *top_n*.

    Parameters
    ----------
    query:
        The user query string.
    chunks:
        List of chunk dictionaries; each must contain a ``text`` key.
    top_n:
        How many top chunks to return.

    Returns
    -------
    list[Dict]
        The highest‑scoring chunks, truncated to *top_n*.
    """
    if not chunks:
        return []

    if _CE_AVAILABLE:
        # Use a lightweight CrossEncoder that works out‑of‑the‑box.
        # The model is small and downloads once.
        try:
            model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-student")
            pairs = [(query, chunk["text"]) for chunk in chunks]
            scores = model.predict(pairs)  # type: ignore
            for chunk, score in zip(chunks, scores):  # type: ignore
                chunk["rerank_score"] = float(score)  # type: ignore
            sorted_chunks = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)  # type: ignore
            return sorted_chunks[:top_n]
        except Exception:  # pragma: no cover
            # fall through to simple fallback
            pass

    # --- fallback: sort by chunk length (longer = more info) ---
    sorted_chunks = sorted(chunks, key=lambda c: len(c.get("text", "")), reverse=True)
    return sorted_chunks[:top_n]