"""Identity surface.

Phase 1 ships :class:`~core.auth.principal.Principal` because the auth middleware and the
storage session layer both need it. Group claim *extraction* and role *authorisation* --
:mod:`core.auth.claims` and :mod:`core.auth.authorization` -- are phase 4 work, per
``docs/implementation.md`` §6.3.
"""

from core.auth.principal import Principal, Role

__all__ = ["Principal", "Role"]
