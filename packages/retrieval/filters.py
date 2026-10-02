from __future__ import annotations

from typing import Optional


def build_acl_predicate(user_groups: list[str] | None = None) -> str:
    """Build the ACL predicate SQL clause.

    Single place where the ACL predicate and metadata predicates are constructed,
    reused by both retrievers so they cannot diverge.
    """
    if not user_groups:
        return "TRUE"  # No restriction
    
    # Build OR condition for each user group
    conditions = " OR ".join([f"acl_tags @> ARRAY[{repr(group)}]" for group in user_groups])
    return f"({conditions})"