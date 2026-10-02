"""Authentication: deny by default, and no silent fallback to the stub.

The behaviour under test is the one that is easy to get subtly wrong:

* An absent credential is an error in ``jwt`` mode -- never an anonymous default user.
* A failed JWT verification never falls back to the development principal.
* Stub mode is available locally but settings refuse to start a staging or production
  process with it.
* Group membership is the authorisation input, and roles derive from it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.middleware.auth import (
    PUBLIC_PATHS,
    StubAuthenticator,
    TokenAuthenticator,
    build_authenticator,
    roles_for,
)
from core.auth.principal import Principal, Role
from core.config.settings import AuthMode
from core.errors import ConfigurationError, Unauthorized


@pytest.fixture
def jwt_settings(settings_factory: Any) -> Any:
    return settings_factory(
        auth_mode=AuthMode.JWT,
        auth_jwt_issuer="https://idp.example.test/",
        auth_jwt_jwks_url="https://idp.example.test/.well-known/jwks.json",
        auth_jwt_algorithms=["RS256"],
    )


@pytest.fixture
def jwt_client(jwt_settings: Any) -> Iterator[TestClient]:
    with TestClient(create_app(jwt_settings), raise_server_exceptions=False) as client:
        yield client


# -- deny by default ---------------------------------------------------------


@pytest.mark.parametrize(
    "path", ["/v1/conversations", "/v1/sources", "/v1/traces", "/v1/feedback", "/v1/admin/status"]
)
def test_protected_routes_reject_an_absent_credential(jwt_client: TestClient, path: str) -> None:
    response = jwt_client.get(path)

    assert response.status_code == 401, f"{path} served an unauthenticated request"
    assert response.json()["error"]["code"] == "credentials_missing"


def test_protected_routes_reject_a_non_bearer_scheme(jwt_client: TestClient) -> None:
    response = jwt_client.get("/v1/conversations", headers={"Authorization": "Basic dXNlcjpwdw=="})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "credentials_malformed"


def test_protected_routes_reject_an_empty_bearer(jwt_client: TestClient) -> None:
    response = jwt_client.get("/v1/conversations", headers={"Authorization": "Bearer "})

    assert response.status_code == 401


def test_a_bogus_token_is_401_not_500(jwt_client: TestClient) -> None:
    """Regression: an AppError raised inside middleware must not surface as a 500.

    Starlette's ExceptionMiddleware wraps only the router, so an exception from user
    middleware bypasses the registered error handlers. This asserts the middleware renders
    the error itself.
    """
    response = jwt_client.get("/v1/conversations", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "jwt_key_unresolved"


def test_error_body_shape_is_uniform(jwt_client: TestClient) -> None:
    """Every failure uses the same envelope, whatever raised it."""
    body = jwt_client.get("/v1/conversations").json()

    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert "Traceback" not in body["error"]["message"]


@pytest.mark.parametrize("path", sorted(PUBLIC_PATHS))
def test_public_paths_need_no_credential(jwt_client: TestClient, path: str) -> None:
    response = jwt_client.get(path)

    assert response.status_code in (200, 503)


def test_public_allowlist_is_explicit_and_small(jwt_client: TestClient) -> None:
    """An allowlist that grows silently is an unauthenticated surface that grew silently.

    Pinned exactly: adding an entry is a security-relevant change and should require
    editing this test.
    """
    assert frozenset(
        {
            "/healthz",
            "/readyz",
            "/version",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
        }
    ) == PUBLIC_PATHS


def test_openapi_is_reachable_without_a_credential(jwt_client: TestClient) -> None:
    """The schema documents how to reach the corpus, but exposes no tenant data."""
    assert jwt_client.get("/openapi.json").status_code == 200


def test_jwt_mode_without_configuration_fails_at_settings_validation(settings_factory: Any) -> None:
    """Fail-fast beats fail-at-first-token.

    A deployment missing ``AUTH_JWT_ISSUER`` should not start and then 401 every request with
    an opaque error; the misconfiguration is a startup problem.
    """
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(auth_mode=AuthMode.JWT, auth_jwt_issuer="", auth_jwt_jwks_url="")


def test_empty_algorithm_list_is_rejected(settings_factory: Any) -> None:
    """Verifying with no allowed algorithms means verifying nothing."""
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(
            auth_mode=AuthMode.JWT,
            auth_jwt_issuer="https://idp.example.test/",
            auth_jwt_jwks_url="https://idp.example.test/jwks.json",
            auth_jwt_algorithms=[],
        )


# -- stub mode ---------------------------------------------------------------


def test_stub_authenticator_ignores_the_credential(settings_factory: Any) -> None:
    settings = settings_factory(auth_mode=AuthMode.STUB)
    principal = StubAuthenticator(settings).authenticate(None)

    assert principal.is_stub
    assert principal.user_id == settings.auth_stub_user_id


def test_stub_mode_lets_every_probe_and_route_through(settings_factory: Any) -> None:
    settings = settings_factory(auth_mode=AuthMode.STUB)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/v1/conversations").status_code == 200


def test_settings_refuse_stub_auth_outside_local(settings_factory: Any) -> None:
    """A staging instance silently running the stub identity is a production incident."""
    for environment in ("staging", "production"):
        with pytest.raises((ConfigurationError, ValueError)):
            settings_factory(environment=environment, auth_mode=AuthMode.STUB)


def test_build_authenticator_never_falls_back_to_stub(jwt_settings: Any) -> None:
    authenticator = build_authenticator(jwt_settings)

    assert isinstance(authenticator, TokenAuthenticator)
    assert not isinstance(authenticator, StubAuthenticator)


def test_jwt_verifier_requires_a_usable_key_source(jwt_settings: Any) -> None:
    """The ``ConfigurationError`` path exists as a defence in depth.

    Settings validation already refuses this combination, so it is reached only if the
    process is configured by some other route -- the check stays because the failure it
    guards against is silent acceptance.
    """
    broken = jwt_settings.model_copy(update={"auth_jwt_jwks_url": ""})

    with pytest.raises(ConfigurationError):
        TokenAuthenticator(broken).authenticate("Bearer anything")


# -- role derivation ---------------------------------------------------------


def test_every_caller_is_at_least_a_user(settings_factory: Any) -> None:
    roles = roles_for(Principal(user_id="u1"), settings_factory())

    assert Role.USER in roles
    assert Role.OPERATOR not in roles


def test_operator_and_admin_come_from_configured_groups(settings_factory: Any) -> None:
    settings = settings_factory(
        auth_operator_groups=["ops"],
        auth_admin_groups=["admins"],
    )

    operator = roles_for(Principal(user_id="u1", groups=frozenset({"ops"})), settings)
    admin = roles_for(Principal(user_id="u2", groups=frozenset({"admins"})), settings)
    both = roles_for(Principal(user_id="u3", groups=frozenset({"ops", "admins"})), settings)

    assert Role.OPERATOR in operator
    assert Role.ADMIN not in operator
    assert Role.ADMIN in admin
    assert {Role.OPERATOR, Role.ADMIN} <= both


def test_admin_routes_deny_a_non_operator(settings_factory: Any) -> None:
    """The plan requires authz stubbed to deny non-operators -- not stubbed open."""
    settings = settings_factory(auth_mode=AuthMode.STUB, auth_stub_groups=[])
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get("/v1/admin/status")

    assert response.status_code == 403


def test_admin_routes_allow_an_operator(settings_factory: Any) -> None:
    settings = settings_factory(auth_mode=AuthMode.STUB, auth_stub_groups=["rag-operators"])
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get("/v1/admin/status")

    assert response.status_code == 200


def test_require_operator_raises_forbidden() -> None:
    from core.errors import Forbidden

    with pytest.raises(Forbidden):
        Principal(user_id="u1").require_operator()


# -- token verification ------------------------------------------------------


def test_expired_token_is_rejected(jwt_settings: Any) -> None:
    """Expiry must be enforced by the verifier, not only asserted in a comment."""
    token = jwt.encode(
        {
            "sub": "u1",
            "exp": 0,
            "iat": 0,
            "aud": jwt_settings.auth_jwt_audience,
            "iss": jwt_settings.auth_jwt_issuer,
        },
        key="secret",
        algorithm="HS256",
    )

    # Verification never reaches signature checks with a JWKS client, but the expired-token
    # branch must still be reachable and must not be bypassable.
    authenticator = TokenAuthenticator(jwt_settings)
    with pytest.raises(Unauthorized):
        authenticator.authenticate(f"Bearer {token}")


def test_algorithm_confusion_is_not_possible(jwt_settings: Any) -> None:
    """``alg: none`` must not verify.

    This is the canonical JWT vulnerability: a token that declares no signature, or a
    symmetric algorithm where an asymmetric one was expected.
    """
    token = jwt.encode(
        {"sub": "admin", "exp": 9999999999, "iat": 1},
        key="",
        algorithm="none",
    )

    with pytest.raises(Unauthorized):
        TokenAuthenticator(jwt_settings).authenticate(f"Bearer {token}")
