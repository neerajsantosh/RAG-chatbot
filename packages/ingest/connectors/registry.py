from __future__ import annotations

from packages.ingest.connectors.local_filesystem import LocalFilesystemConnector


def resolve_connector(source_type: str = "local_filesystem", **options: object) -> type[Connector]:
    """Resolve a source type from config to a connector class."""
    mapping = {
        "local_filesystem": LocalFilesystemConnector,
    }
    cls = mapping.get(source_type)
    if cls is None:
        raise ValueError(f"Unknown connector type: {source_type}")
    return cls