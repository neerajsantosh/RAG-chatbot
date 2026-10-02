"""Request-scoped dependencies.

FastAPI's dependency system is where the principal gets bound to a request, and it is the
reason no route signature needs a user id, a token or a session handle.

The important property: a route that needs a caller declares it, and a route that does not
need one cannot accidentally use one. :func:`optional_principal` exists only for the health
endpoints, and it is separate from :func:`current_principal` so that "I am not asking who
this is" and "I am asking and found nobody" do not look the same.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from api.middleware.auth import Authenticator, build_authenticator
from core.auth.principal import Principal
from core.config.settings import Settings, get_settings
from core.errors import Unauthorized
from core.telemetry import get_recorder
from core.telemetry.spans import SpanRecorder
from storage.db.engine import DatabaseEngine, get_engine

__all__ = [
    "CurrentPrincipal",
    "DatabaseDep",
    "OptionalPrincipal",
    "RecorderDep",
    "SettingsDep",
    "authenticator_dep",
    "current_principal",
    "database_dep",
    "optional_principal",
    "recorder_dep",
    "settings_dep",
]


def settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]


def authenticator_dep(settings: SettingsDep) -> Authenticator:
    return build_authenticator(settings)


def current_principal(
    request: Request, authenticator: Annotated[Authenticator, Depends(authenticator_dep)]
) -> Principal:
    """The authenticated caller. Raises :class:`Unauthorized` if there is not one."""
    principal: Principal | None = getattr(request.state, "principal", None)
    if principal is None:
        # Reached when the auth middleware is not installed. Failing loudly here beats
        # serving an unauthenticated request, and the message names the actual cause.
        raise Unauthorized(
            "no principal on the request; the authentication middleware is not installed",
            code="auth_middleware_missing",
        )
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def optional_principal(request: Request) -> Principal | None:
    """The caller if one was established, else ``None``.

    For unauthenticated endpoints only. Any endpoint that acts on data must use
    :func:`current_principal` instead.
    """
    principal: Principal | None = getattr(request.state, "principal", None)
    return principal


OptionalPrincipal = Annotated[Principal | None, Depends(optional_principal)]


def database_dep() -> DatabaseEngine:
    return get_engine()


DatabaseDep = Annotated[DatabaseEngine, Depends(database_dep)]


def recorder_dep() -> SpanRecorder:
    return get_recorder()


RecorderDep = Annotated[SpanRecorder, Depends(recorder_dep)]
