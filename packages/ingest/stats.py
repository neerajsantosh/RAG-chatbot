from __future__ import annotations

from packages.ingest.models import Chunk


def chunk_statistics(chunks: list[Chunk]) -> dict:
    """Chunk statistics report: counts, token distribution, over-budget percentage."""
    if not chunks:
        return {
            "total_chunks": 0,
            "mean_token_count": 0,
            "median_token_count": 0,
            "pct_over_budget": 0,
            "worst_offenders": [],
        }

    token_counts = [c.token_count for c in chunks]
    total = len(chunks)
    mean = sum(token_counts) / total
    sorted_counts = sorted(token_counts)
    median = sorted_counts[len(sorted_counts) // 2]

    # Define budget as 512 tokens (configurable later)
    budget = 512
    over_budget = sum(1 for tc in token_counts if tc > budget)
    pct_over = (over_budget / total) * 100 if total > 0 else 0

    # worst offenders: chunks exceeding budget by most tokens
    worst = sorted(
        [{"chunk_text": c.text[:80], "token_count": c.token_count} for c in chunks if c.token_count > budget],
        key=lambda x: x["token_count"],
        reverse=True,
    )[:5]

    return {
        "total_chunks": total,
        "mean_token_count": round(mean, 2),
        "median_token_count": median,
        "pct_over_budget": round(pct_over, 2),
        "worst_offenders": worst,
    }