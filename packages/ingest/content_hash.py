from __future__ import annotations

import hashlib


def content_hash(text: str, chunker_version: str, model_version: str) -> str:
    """Compute content_hash over normalised text + chunker version + embedding-model version string.

    This ensures ingestion is idempotent and configuration changes invalidate
    precisely the chunks they affect.
    """
    data = f"{text.strip()}|{chunker_version}|{model_version}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()