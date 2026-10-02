"""Transaction-scoped principal binding.

This module is the mechanism behind architecture driver D5 -- access control cannot leak --
and behind the ``app.user_groups`` session variable the RLS policies in
:mod:`storage.rls` read.

The rule it enforces: **a session that forgets to bind a principal gets no access, not all
access.** A transaction that opens without calling :func:`principal_transaction` runs with
an empty group list, so every ``restricted`` document is invisible while ``org`` documents
stay visible. That default is the safe one; the inverse default would turn a forgotten call
site into a data breach rather than an outage.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection

from core.auth.principal import Principal
from storage.db.engine import DatabaseEngine

__all__ = [
    "GROUPS_SETTING",
    "TENANT_SETTING",
    "bind_principal",
    "clear_principal",
    "principal_transaction",
]

GROUPS_SETTING = "app.user_groups"
"""Session variable holding the caller's group list, as a PostgreSQL array literal."""

TENANT_SETTING = "app.tenant_id"
"""Reserved for the multi-tenant work excluded from v1 (PRD §3, assumption A3).

Set alongside the groups whenever a tenant column exists, so adding tenancy later is a
policy change rather than a query rewrite across every repository.
"""


def _as_pg_array(values: frozenset[str]) -> str:
    """Render groups as a PostgreSQL array literal.

    Each element is quoted and escaped so a group name containing a comma, a quote or a
    backslash cannot alter the array's structure. ``set_config`` receives the result as a
    parameter value, never as parsed SQL.
    """
    escaped = [value.replace("\\", "\\\\").replace('"', '\\"') for value in sorted(values)]
    return "{" + ",".join(f'"{value}"' for value in escaped) + "}"


def bind_principal(
    conn: Connection[Any],
    principal: Principal,
    *,
    tenant_id: str | None = None,
) -> None:
    """Bind a verified principal to the current transaction.

    Must run before any query touching ``document`` or ``chunk``. Deliberately not marked
    ``is_local`` in PostgreSQL: with ``is_local=true`` the value resets at the end of each
    statement, so a statement issued without binding would silently inherit the *previous*
    caller's groups on a pooled connection.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, false), set_config(%s, %s, false)",
            (GROUPS_SETTING, _as_pg_array(principal.groups), TENANT_SETTING, tenant_id or ""),
        )


def clear_principal(conn: Connection[Any]) -> None:
    """Remove any bound principal. Run on pool return so the next borrower starts clean."""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, false), set_config(%s, %s, false)",
            (GROUPS_SETTING, "{}", TENANT_SETTING, ""),
        )


@contextmanager
def principal_transaction(
    engine: DatabaseEngine,
    principal: Principal,
    *,
    tenant_id: str | None = None,
) -> Iterator[Connection[Any]]:
    """Open a transaction with the principal already bound.

    The only supported way to touch a table carrying an RLS policy. A bare
    ``engine.connection()`` remains correct for tables without access control and wrong for
    everything else.
    """
    with engine.connection() as conn:
        bind_principal(conn, principal, tenant_id=tenant_id)
        yield conn
