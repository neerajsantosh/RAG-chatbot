"""The authenticated caller.

Everything downstream of authentication receives a :class:`Principal` and nothing else.
That constraint is deliberate and load-bearing:

* It makes the identity a value rather than ambient state. A repository that forgets to
  check permissions cannot accidentally consult "whoever is logged in", because there is no
  ambient caller to consult.
* It is frozen, so it cannot be widened mid-request by a later stage.
* It carries no token, no expiry and no claims bag. Nothing downstream needs them, so
  keeping them out means no downstream stage can accidentally log a credential.

Role *assignment* lives in :mod:`api.middleware.auth` for now and moves to
:mod:`core.auth.authorization` in phase 4. Keeping ``Principal`` free of any dependency on
:mod:`core.config.settings` is what allows tests to construct one without an environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Principal", "Role"]


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated caller: an id, the groups they belong to, and their roles."""

    user_id: str
    groups: frozenset[str] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=frozenset)
    is_stub: bool = False
    """True for the local development identity. Phase 4 asserts this is never true in a
    deployed environment, which is what makes ``AUTH_MODE=stub`` safe to develop against
    and unsafe to ship."""

    def has_group(self, group: str) -> bool:
        return group in self.groups

    def has_any_group(self, groups: frozenset[str] | set[str]) -> bool:
        return bool(self.groups & groups)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @property
    def is_operator(self) -> bool:
        return self.has_role(Role.OPERATOR)

    @property
    def is_admin(self) -> bool:
        return self.has_role(Role.ADMIN)

    def require_operator(self) -> None:
        """Raise unless the caller is an operator. Used by admin routes (FR-30, FR-31)."""
        from core.errors import Forbidden

        if not self.is_operator:
            raise Forbidden("operator role required", details={"required_role": Role.OPERATOR})

    def require_admin(self) -> None:
        from core.errors import Forbidden

        if not self.is_admin:
            raise Forbidden("admin role required", details={"required_role": Role.ADMIN})

    def to_log_fields(self) -> dict[str, str | int | bool]:
        """Fields safe to log: identity and counts only, never the token.

        ``group_count`` rather than ``groups``: group membership is access-control data,
        and a log aggregation that can list it can enumerate who can see what.
        """
        return {
            "user_id": self.user_id,
            "group_count": len(self.groups),
            "role_count": len(self.roles),
            "is_stub": self.is_stub,
        }


class Role:
    """Role names. Plain constants so they can be compared without importing an enum."""

    OPERATOR = "operator"
    ADMIN = "admin"
    USER = "user"
