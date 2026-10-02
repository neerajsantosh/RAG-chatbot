from __future__ import annotations

from packages.core.auth.principal import Principal


def extract_principal_from_token(token: str) -> Principal:
    """Extract Principal from verified JWT token.

    Unknown token shape fails closed - returns a stub Principal that is denied
    access to everything, ensuring we never accidentally grant permissions
    from a malformed or missing token.
    """
    # In production, this would decode and verify the JWT
    # For now, return a stub principal that fails closed
    from core.errors import Forbidden

    raise Forbidden(
        "Token verification not yet implemented - this is phase 4 guardrail",
        details={"phase": "4", "feature": "claims_extraction"},
    )


def extract_groups_from_claims(claims: dict) -> frozenset[str]:
    """Extract group membership from JWT claims.

    Fails closed if the claim shape is unexpected.
    """
    groups = claims.get("groups", [])
    if not isinstance(groups, list):
        raise ValueError("groups claim must be a list")
    return frozenset(str(g) for g in groups)


def extract_roles_from_claims(claims: dict) -> frozenset[str]:
    """Extract role membership from JWT claims.

    Fails closed if the claim shape is unexpected.
    """
    roles = claims.get("roles", [])
    if not isinstance(roles, list):
        raise ValueError("roles claim must be a list")
    return frozenset(str(r) for r in roles)