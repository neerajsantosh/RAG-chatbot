from __future__ import annotations

from typing import Sequence, Dict, Any

from packages.retrieval.models import Chunk


class IndexStats:
    """Index health: coverage, null embeddings, orphans, stale documents, dimension mismatches."""

    @staticmethod
    def compute_health_report(chunks: Sequence[Chunk], total_expected: int) -> Dict[str, Any]:
        """Compute index health report from chunk data."""
        total_chunks = len(chunks)

        # Count chunks with embeddings (non-null)
        chunks_with_embedding = sum(
            1 for c in chunks if c.embedding is not None and len(c.embedding) > 0
        )

        # Count orphans (chunks without a valid document link)
        orphans = sum(
            1 for c in chunks if not c.source_file
        )

        # Dimension consistency check
        dimension_errors = 0
        sample_dim = None
        for c in chunks[:10]:  # Sample check
            if c.embedding is not None:
                sample_dim = len(c.embedding)
                break

        if sample_dim is not None:
            dimension_errors = sum(
                1 for c in chunks if c.embedding is not None and len(c.embedding) != sample_dim
            )

        pct_covered = (chunks_with_embedding / total_chunks * 100) if total_chunks > 0 else 0
        pct_orphans = (orphans / total_chunks * 100) if total_chunks > 0 else 0
        pct_dimension_errors = (dimension_errors / total_chunks * 100) if total_chunks > 0 else 0

        return {
            "total_chunks": total_chunks,
            "chunks_with_embedding": chunks_with_embedding,
            "pct_covered": round(pct_covered, 2),
            "orphans": orphans,
            "pct_orphans": round(pct_orphans, 2),
            "dimension": sample_dim,
            "dimension_errors": dimension_errors,
            "pct_dimension_errors": round(pct_dimension_errors, 2),
        }