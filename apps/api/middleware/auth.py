"""Authentication: who is calling, and how we know.

Phase 1 ships two modes and they exist for opposite reasons. ``stub`` is what makes the
system runnable today with no identity provider. ``jwt`` is the real thing, wired now so
that phase 4 is a matter of configuring an issuer rather than restructuring the request
path.

Two decisions worth stating, because both are the kind of thing that is easy to get subtly
wrong and hard to notice until an incident:

**An absent credential is an error, not an anonymous user.** There is no code path that
treats a missing header as "some default principal". Development convenience comes from the
stub mode being explicit, not from the production path accepting anonymous callers.

**Signature verification is mandatory.** ``jwt.decode`` is called with a resolved key and a
required list of algorithms. Both arguments are load-bearing: passing ``verify=False``, or
letting the token's own ``alg`` header choose the algorithm, would make any token
forgeable by anyone who can reach the endpoint.

Role assignment lives here rather than in :mod:`core.auth.principal`, which keeps
``Principal`` free of any dependency on settings and therefore constructible in tests
without an environment.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.errors import app_error_response
from core.auth.principal import Principal, Role
from core.config.settings import AuthMode, Settings
from core.errors import ConfigurationError, ProviderAuthError, Unauthorized
from core.logging import get_logger, log_extra

__all__ = [
    "PUBLIC_PATHS",
    "AuthMiddleware",
    "Authenticator",
    "StubAuthenticator",
    "TokenAuthenticator",
    "roles_for",
    "verify_bearer_token",
]

_logger = get_logger(__name__)

#: Endpoints that must answer without a credential. This is an explicit allowlist rather
#: than "anything without a principal passes", because the second form makes every new
#: unprotected endpoint a silent data leak.
#:
#: The schema and docs routes are included so the generated OpenAPI document stays
#: reachable -- they expose the shape of the API but no tenant data, and phase 4 replaces
#: them with a configuration that disables them outside local environments.
PUBLIC_PATHS = frozenset(
    {
        "/healthz",
        "/readyz",
        "/version",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)

BearerToken = str

JWKSClientFactory = Callable[[str], PyJWKClient]


def roles_for(principal: Principal, settings: Settings) -> frozenset[str]:
    """Derive application roles from the principal's groups.

    Every authenticated caller is at least a ``user``; operator and admin come from
    configured group membership. Group membership is the authorisation input because it is
    what the identity provider already maintains -- inventing a second membership store
    here would be a system nobody can audit.
    """
    roles = {Role.USER}
    if principal.has_any_group(set(settings.auth_operator_groups)):
        roles.add(Role.OPERATOR)
    if principal.has_any_group(set(settings.auth_admin_groups)):
        roles.add(Role.ADMIN)
    return frozenset(roles)


def _strip_bearer(header: str | None) -> BearerToken:
    if not header:
        raise Unauthorized(
            "authorization header is missing",
            code="credentials_missing",
        )
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        # The scheme is echoed back because "wrong scheme" is a client bug worth naming,
        # and the header itself contains no secret.
        raise Unauthorized(
            f"expected an 'Authorization: Bearer <token>' header, "
            f"got scheme {scheme or '(none)'!r}",
            code="credentials_malformed",
        )
    return token.strip()


def verify_bearer_token(
    token: str, settings: Settings, *, client: PyJWKClient | None = None
) -> dict[str, Any]:
    """Verify a bearer token and return its claims.

    Raises :class:`Unauthorized` on anything untrustworthy. The underlying exception is
    logged by type only -- a JWT error message can echo token fragments, and NFR-16 does not
    negotiate.
    """
    if not settings.auth_jwt_issuer or not settings.auth_jwt_jwks_url:
        raise ConfigurationError(
            "AUTH_MODE=jwt requires both AUTH_JWT_ISSUER and AUTH_JWT_JWKS_URL",
            code="jwt_not_configured",
        )

    algorithms = list(settings.auth_jwt_algorithms)
    if not algorithms:
        raise ConfigurationError(
            "AUTH_JWT_ALGORITHMS must not be empty; refusing to verify tokens",
            code="jwt_algorithms_missing",
        )

    key_client = client or PyJWKClient(
        settings.auth_jwt_jwks_url,
        # Short cache so a key rotation takes effect without a restart, while a revoked
        # key still stops being honoured quickly.
        cache_jwk_set=True,
        lifespan=300,
    )

    try:
        signing_key = key_client.get_signing_key_from_jwt(token)
    except Exception as exc:
        _logger.warning(
            "jwt signing key could not be resolved",
            extra={"error_type": type(exc).__name__},
        )
        raise Unauthorized(
            "bearer token is not verifiable", code="jwt_key_unresolved"
        ) from exc

    try:
        return jwt.decode(
            token,
            signing_key.key,
            # Both of these are deliberate. Without the explicit algorithm list a token
            # could choose its own, and without an audience check a token minted for a
            # different service in the same identity provider would be accepted here.
            algorithms=algorithms,
            audience=settings.auth_jwt_audience or None,
            issuer=settings.auth_jwt_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("bearer token has expired", code="jwt_expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise Unauthorized("bearer token is for another audience", code="jwt_audience") from exc
    except jwt.InvalidIssuerError as exc:
        raise Unauthorized("bearer token is from another issuer", code="jwt_issuer") from exc
    except jwt.MissingRequiredClaimError as exc:
        _logger.warning("jwt missing required claim", extra={"error_type": type(exc).__name__})
        raise Unauthorized(
            "bearer token is missing a required claim", code="jwt_claim_missing"
        ) from exc
    except jwt.InvalidTokenError as exc:
        # Signature failures, malformed tokens and bad claim types all land here.
        _logger.warning("jwt rejected", extra={"error_type": type(exc).__name__})
        raise Unauthorized("bearer token is invalid", code="jwt_invalid") from exc


class StubAuthenticator:
    """Returns the configured development principal, ignoring any credential.

    Local and CI only. :mod:`core.config.settings` refuses to start a staging or production
    deployment with ``AUTH_MODE=stub``, and ``/readyz`` reports it as a degraded
    environment, so this cannot become a way to run the real deployment without identity.
    """

    __slots__ = ("_settings",)

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authenticate(self, authorization: str | None) -> Principal:
        principal = Principal(
            user_id=self._settings.auth_stub_user_id,
            groups=frozenset(self._settings.auth_stub_groups),
            is_stub=True,
        )
        # Roles are applied here rather than baked into the stub so that role derivation is
        # exercised by the stub path too. A stub that skipped this would let a bug in
        # roles_for() reach production untouched.
        return _with_roles(principal, self._settings)


class TokenAuthenticator:
    """Verifies a bearer token against the configured identity provider."""

    __slots__ = ("_client", "_settings")

    def __init__(self, settings: Settings, *, client: PyJWKClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def authenticate(self, authorization: str | None) -> Principal:
        token = _strip_bearer(authorization)
        claims = verify_bearer_token(token, self._settings, client=self._client)

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise Unauthorized("bearer token has no usable subject", code="jwt_subject_missing")

        raw_groups = claims.get("groups", claims.get("roles", []))
        if isinstance(raw_groups, str):
            # A single string is how many IdPs emit a group claim for one-group users.
            groups = frozenset({raw_groups})
        elif isinstance(raw_groups, list):
            groups = frozenset(str(item) for item in raw_groups)
        else:
            raise Unauthorized(
                "bearer token group claim is not a list or string", code="jwt_groups_invalid"
            )

        return _with_roles(
            Principal(user_id=subject, groups=groups, is_stub=False), self._settings
        )


def _with_roles(principal: Principal, settings: Settings) -> Principal:
    from dataclasses import replace

    return replace(principal, roles=roles_for(principal, settings))


def build_authenticator(settings: Settings) -> StubAuthenticator | TokenAuthenticator:
    """Select the authenticator. Never falls back to the stub on a JWT failure."""
    if settings.auth_mode is AuthMode.JWT:
        return TokenAuthenticator(settings)
    return StubAuthenticator(settings)


# Referenced by architecture.md FR-29 as the phase 1 seam. Kept as an alias so the
# dependency in api/dependencies.py names one thing.
Authenticator = StubAuthenticator | TokenAuthenticator


def provider_error(reason: str) -> ProviderAuthError:
    """A uniform error for identity-provider failures that are not the caller's fault."""
    return ProviderAuthError(f"identity provider rejected the request: {reason}", code="idp_error")


class AuthMiddleware(BaseHTTPMiddleware):
    """Establishes the caller's :class:`Principal` before any handler runs.

    Runs *outside* the rate limiter so the limiter can key on the principal, and inside the
    request-id middleware so a rejected request still has a correlation id.

    Two behaviours worth stating plainly:

    **An unauthenticated request fails here, with 401.** The handler never runs, so no route
    can forget to check. This is the "deny by default" in the architecture: the safe
    behaviour is the one that happens when nobody remembered anything.

    **A request that already has a principal is not re-authenticated.** Authentication is a
    per-request decision made once. Re-verifying a signature deeper in the stack would make
    two disagreeing principals possible, and a handler could then read the one it set rather
    than the one the chain authenticated.
    """

    def __init__(
        self,
        app: object,
        *,
        authenticator: Authenticator,
        public_paths: frozenset[str] | None = None,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._authenticator = authenticator
        self._public_paths = PUBLIC_PATHS if public_paths is None else public_paths

    def is_public(self, path: str) -> bool:
        return path in self._public_paths

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if getattr(request.state, "principal", None) is None and not self.is_public(
            request.url.path
        ):
            try:
                principal = self._authenticator.authenticate(
                    request.headers.get("Authorization")
                )
            except Unauthorized as exc:
                # Type only: an exception message from token verification can echo token
                # fragments, and NFR-16 does not negotiate on the error path either.
                _logger.info(
                    "authentication rejected",
                    extra=log_extra(
                        method=request.method,
                        path=request.url.path,
                        request_id=getattr(request.state, "request_id", ""),
                    ),
                )
                # Rendered here rather than re-raised: an exception from user middleware
                # passes outside Starlette's ExceptionMiddleware, so it would never reach
                # the registered AppError handler and the caller would see a 500 for what is
                # a 401. See api.errors.app_error_response.
                return app_error_response(request, exc)

            request.state.principal = principal
            request.state.authenticated = True

        return await call_next(request)
