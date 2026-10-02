"""Persistence surface.

Phase 1 establishes the boundaries and the connection lifecycle, not the schema. The
repository ports in :mod:`storage.ports` are the contract; the concrete corpus tables land
in phase 2 and vector indexes in phase 3.

Two things are real in phase 1 because they are cheap now and expensive later:

* **Row-level security**, enabled from the start (architecture §10.3). Retrofitting RLS
  onto tables that already hold documents means auditing every existing query, and the
  safety net has to exist before the data does.
* **The principal's groups set on every transaction**, via :func:`storage.db.session`.
  A session that forgets to set them gets an empty group list, which RLS reads as "no
  access" -- deny by default.
"""

from storage.db.engine import DatabaseEngine, get_engine, reset_engine
from storage.ports import (
    ChunkRepository,
    ConfigStore,
    DocumentRepository,
    ObjectStore,
    TraceStore,
)

__all__ = [
    "ChunkRepository",
    "ConfigStore",
    "DatabaseEngine",
    "DocumentRepository",
    "ObjectStore",
    "TraceStore",
    "get_engine",
    "reset_engine",
]
