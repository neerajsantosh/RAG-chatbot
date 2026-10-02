from __future__ import annotations

import re
from packages.ingest.models import Chunk


_INSTRUCTION_PATTERN: Final = re.compile(
    r"\b(?:ignore|override|disregard|forget|not|stop)\s+.*?(?:instructions|rules|policies|constraints)\b",
    re.IGNORECASE,
)


def injection_scan(chunk: Chunk) -> bool:
    """Flags instruction-like patterns in chunk text; sets is_suspicious.

    Returns True if the chunk contains suspicious instruction patterns.
    """
    return bool(_INSTRUCTION_PATTERN.search(chunk.text))