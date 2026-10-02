from __future__ import annotations

from packages.core.auth.principal import Principal, Role


def check_document_access(principal: Principal, required_role: str | None = None) -> None:
    """Check that the principal has the required role to access documents.

    Deny by default - the principal must explicitly have the required role.
    Used by document routes to enforce FR-30, FR-31.
    """
    if required_role and not principal.has_role(required_role):
        from core.errors import Forbidden
        raise Forbidden(
            f"{required_role} role required to access documents",
            details={"required_role": required_role, "user_role": 
                     ", ".join(sorted(principal.roles)) if principal.roles else "none"},
        )


def check_group_membership(principal: Principal, required_groups: frozenset[str]) -> None:
    """Check that the principal belongs to at least one of the required groups.

    Deny by default. Used for ACL-filtered retrieval.
    """
    if not principal.has_any_group(required_groups):
        from core.errors import Forbidden
        raise Forbidden(
            "Insufficient group membership for this resource",
            details={
                "required_groups": ", ".join(sorted(required_groups)),
                "user_groups": ", ".join(sorted(principal.groups)),
            },
        )


def deny_by_default(principal: Principal, message: str = "Access denied") -> None:
    """Raise Forbidden if the principal is not an operator or admin.

    Used as a safety net for endpoints that should only be accessible
    by operators/admins.
    """
    if not principal.is_operator and not principal.is_admin:
        from core.errors import Forbidden
        raise Forbidden(message)