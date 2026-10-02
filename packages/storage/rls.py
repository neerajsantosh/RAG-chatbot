"""Row-level security management.

RLS is the safety net *beneath* the ACL predicate that phase 3 puts in every query. The
predicate is the control; RLS is what makes a mistake in the predicate an outage rather than
a breach.

The ordering is deliberate and is the reason this module is separate from
:mod:`storage.db.migrate`: the policy text is defined and reviewed independently of any
particular table, and attaching it is a phase-4 action that can therefore be tested against
a phase-3 corpus.

Behaviour to rely on:

* ``org``-visible documents are readable by any bound principal.
* ``restricted`` documents require a matching group in ``app.user_groups``.
* An unbound transaction sees ``{}`` and therefore sees nothing restricted.
* Soft-deleted documents are never readable, regardless of group.
"""

from __future__ import annotations

from typing import Final

from core.logging import get_logger, log_extra

__all__ = [
    "POLICY_DEFINITIONS",
    "document_policy_sql",
    "enable_rls",
    "rls_tables",
    "verify_rls_enabled",
]

_logger = get_logger(__name__)

rls_tables: Final[tuple[str, ...]] = ("document", "chunk")
"""Tables carrying access control. Adding a table here is a security review event."""

POLICY_DEFINITIONS: Final[dict[str, str]] = {
    "document": """
        USING (
            deleted_at IS NULL
            AND principal_may_read(acl_tags, visibility)
        )
        WITH CHECK (
            deleted_at IS NULL
            AND principal_may_read(acl_tags, visibility)
        )
    """,
    "chunk": """
        USING (
            active
            AND document_id IN (
                SELECT id FROM document
            )
        )
    """,
}
"""Per-table policy SQL.

``document`` states the rule directly. ``chunk`` inherits it by subquery against
``document``, so a chunk can never be visible while its document is not -- which removes a
whole class of bug where an index returns a chunk id whose document the citation resolver
then refuses, leaving the user with a citation that leads nowhere.
"""


def document_policy_sql(table: str) -> str:
    """The full ``ALTER TABLE ... ENABLE ROW LEVEL SECURITY`` plus ``CREATE POLICY`` script."""
    if table not in POLICY_DEFINITIONS:
        raise ValueError(f"no RLS policy defined for {table!r}; known tables: {list(rls_tables)}")

    return f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;

        DROP POLICY IF EXISTS {table}_acl ON {table};
        CREATE POLICY {table}_acl ON {table}
        {POLICY_DEFINITIONS[table]};
    """


def enable_rls(conn: object) -> list[str]:
    """Attach the policies. Idempotent.

    ``FORCE ROW LEVEL SECURITY`` is deliberate: without it, a table owner bypasses its own
    policies. The application role must not own the corpus tables.
    """
    applied: list[str] = []
    for table in rls_tables:
        with conn.cursor() as cursor:  # type: ignore[attr-defined]
            cursor.execute(document_policy_sql(table))
        applied.append(table)
        _logger.info("row level security enabled", extra=log_extra(table=table))
    return applied


def verify_rls_enabled(conn: object) -> dict[str, bool]:
    """Whether RLS is actually on for each protected table.

    A phase-4 gate item. ``relrowsecurity`` says the table has RLS enabled;
    ``relforcerowsecurity`` says the owner cannot bypass it. Checking only the first would
    miss the more common and more dangerous gap.
    """
    with conn.cursor() as cursor:  # type: ignore[attr-defined]
        cursor.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname = ANY(%s)",
            (list(rls_tables),),
        )
        rows = cursor.fetchall()

    return {
        row["relname"]: bool(row["relrowsecurity"]) and bool(row["relforcerowsecurity"])
        for row in rows
    }
