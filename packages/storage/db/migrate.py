"""Minimal forward-only migration runner.

Deliberately not a migration framework. Phase 1 needs ordered, recorded, transactional SQL
execution and nothing else; adopting Alembic or Flyway would add a dependency and a
configuration language for behaviour that fits in one file.

Usage::

    python -m storage.db.migrate
    python -m storage.db.migrate --status
    python -m storage.db.migrate --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from core.config.settings import get_settings
from core.errors import ConfigurationError
from core.logging import configure_logging, get_logger, log_extra
from storage.db.engine import DatabaseEngine, get_engine

__all__ = ["Migration", "apply_migrations", "discover_migrations", "main", "status"]

_logger = get_logger(__name__)

MIGRATIONS_DIR: Final[Path] = Path(__file__).parent / "migrations"
_VERSION_PATTERN: Final = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str

    @property
    def label(self) -> str:
        return f"{self.version}_{self.name}"


def discover_migrations(directory: Path | None = None) -> list[Migration]:
    """Return every migration in the directory, ordered by version.

    Raises on a malformed filename rather than skipping it. A migration named ``add_x.sql``
    that sorts nowhere is the kind of thing that gets applied in production and not in
    development.
    """
    location = directory or MIGRATIONS_DIR
    if not location.is_dir():
        raise ConfigurationError(
            f"migrations directory not found: {location}", code="migrations_missing"
        )

    found: list[Migration] = []
    for path in sorted(location.glob("*.sql")):
        match = _VERSION_PATTERN.match(path.name)
        if match is None:
            raise ConfigurationError(
                f"migration filename must be NNNN_name.sql, got {path.name}",
                code="migration_name_invalid",
                details={"path": str(path)},
            )
        version, name = match.group(1), match.group(2)
        found.append(
            Migration(version=version, name=name, path=path, sql=path.read_text(encoding="utf-8"))
        )

    seen_versions: set[str] = set()
    duplicates: set[str] = set()
    for item in found:
        if item.version in seen_versions:
            duplicates.add(item.version)
        seen_versions.add(item.version)
    if duplicates:
        raise ConfigurationError(
            f"duplicate migration versions: {sorted(duplicates)}",
            code="migration_version_duplicate",
        )

    return found


def _applied_versions(conn: object) -> set[str]:
    with conn.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS schema_migration ("
            "version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        cursor.execute("SELECT version FROM schema_migration")
        rows = cursor.fetchall()
    return {row["version"] if isinstance(row, dict) else row[0] for row in rows}


def status(engine: DatabaseEngine) -> list[dict[str, str]]:
    """Applied and pending versions, oldest first."""
    migrations = discover_migrations()
    with engine.connection() as conn:
        applied = _applied_versions(conn)

    return [
        {
            "version": item.version,
            "name": item.name,
            "state": "applied" if item.version in applied else "pending",
        }
        for item in migrations
    ]


def apply_migrations(
    engine: DatabaseEngine | None = None,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Apply every pending migration. Returns the versions applied.

    Each migration runs in its own transaction together with its bookkeeping row, so a
    failure leaves the database at the last version that fully applied rather than in a
    partially migrated state.
    """
    active = engine or get_engine()
    migrations = discover_migrations()

    with active.connection() as conn:
        applied = _applied_versions(conn)
        pending = [item for item in migrations if item.version not in applied]

    if not pending:
        _logger.info("no pending migrations", extra=log_extra(migration_count=len(migrations)))
        return []

    if dry_run:
        _logger.info(
            "dry run: migrations that would be applied",
            extra=log_extra(pending_count=len(pending), versions=[item.label for item in pending]),
        )
        return [item.version for item in pending]

    completed: list[str] = []
    for migration in pending:
        with active.connection() as conn, conn.cursor() as cursor:
            cursor.execute(migration.sql)
            cursor.execute(
                "INSERT INTO schema_migration (version) VALUES (%s) "
                "ON CONFLICT (version) DO NOTHING",
                (migration.version,),
            )
        completed.append(migration.version)
        _logger.info("migration applied", extra=log_extra(migration=migration.label))

    return completed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="storage.db.migrate", description=__doc__)
    parser.add_argument("--status", action="store_true", help="show applied and pending versions")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would be applied, apply nothing"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, fmt=settings.log_format, environment=settings.environment)

    engine = DatabaseEngine(settings)
    try:
        if args.status:
            for row in status(engine):
                print(f"{row['state']:<8} {row['version']}_{row['name']}")
            return 0

        applied = apply_migrations(engine, dry_run=args.dry_run)
        print(f"applied {len(applied)} migration(s)")
        return 0
    except Exception as exc:  # noqa: BLE001 - a CLI reports rather than raises
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
