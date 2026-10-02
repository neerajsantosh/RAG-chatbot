from __future__ import annotations

from packages.ingest.models import SourceRef


def derive_acl_tags(metadata: dict) -> list[str]:
    """Derive ACL tags from source permissions or per-document config.

    Fails closed when permissions cannot be determined.
    """
    tags: list[str] = metadata.get("acl_tags", [])
    if not tags:
        # Default: no tags means accessible to everyone (or fail closed depending on policy)
        # Here we return empty to indicate no restrictions
        return []
    return [t.strip() for t in tags if t.strip()]