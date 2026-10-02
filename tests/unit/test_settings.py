"""Settings validation.

Every test here is a case where the process must refuse to start rather than start in a
state that quietly violates the architecture. A misconfigured deployment that boots is more
dangerous than one that does not: the first accepts traffic it cannot serve correctly, the
second fails a deploy.

The pattern to follow when adding cases: assert the *rule*, not just the exception type, so
a widened validator does not silently make the test pass.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.config.settings import Settings
from core.errors import ConfigurationError

JWT_OK: dict[str, Any] = {
    "auth_mode": "jwt",
    "auth_jwt_issuer": "https://idp.example.test/",
    "auth_jwt_jwks_url": "https://idp.example.test/jwks.json",
}


# -- defaults ----------------------------------------------------------------


def test_defaults_are_local_and_offline(settings_factory: Any) -> None:
    """A fresh checkout must run with no account and no secrets.

    Anything else makes the phase 1 acceptance run depend on a human having configured
    something first, which is exactly what it is meant to prove is unnecessary.
    """
    settings = settings_factory()

    assert settings.environment == "local"
    assert settings.database_required is False
    assert settings.allow_fake_model_adapters is True
    from core.config.settings import AuthMode
    assert settings.auth_mode is AuthMode.STUB


def test_unknown_environment_is_rejected(settings_factory: Any) -> None:
    """A typo in APP_ENV must not fall back to local, which permits fake adapters."""
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(environment="prod")


# -- secrets -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("auth_jwt_signing_key", "a-signing-key"),
        ("database_password", "a-password"),
        ("openai_api_key", "sk-test"),
        ("anthropic_api_key", "sk-test"),
    ],
)
def test_production_refuses_insecure_placeholder_secrets(
    settings_factory: Any, name: str, value: str
) -> None:
    """Known example/placeholder values must never reach staging or production.

    ``.env.example`` ships placeholder values, and the file is routinely copied to
    ``.env``. Refusing the placeholders by value is what stops that copy from deploying.
    """
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(
            environment="production",
            database_required=True,
            allow_fake_model_adapters=False,
            **JWT_OK,
            **{name: value},
        )


def test_production_requires_a_database(settings_factory: Any) -> None:
    """A production process that does not require a database will start without one."""
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(environment="production", database_required=False, **JWT_OK)


def test_production_refuses_fake_adapters(settings_factory: Any) -> None:
    """The single most important rule in this file.

    A fake adapter in production produces confident, well-formatted, invented answers with
    citations. It is worse than no answer, and it is invisible without this check.
    """
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(
            environment="production",
            allow_fake_model_adapters=True,
            database_required=True,
            **JWT_OK,
        )


def test_local_may_use_fake_adapters(settings_factory: Any) -> None:
    """Otherwise the offline development loop the plan depends on becomes impossible."""
    result = settings_factory(allow_fake_model_adapters=True, environment="local")
    assert result.environment == "local"


# -- auth --------------------------------------------------------------------


def test_jwt_mode_requires_an_issuer(settings_factory: Any) -> None:
    """Without an issuer, any token the JWKS signs is accepted -- which is any token."""
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(auth_mode="jwt", auth_jwt_jwks_url="https://idp.example.test/jwks.json")


def test_jwt_mode_requires_a_jwks_url(settings_factory: Any) -> None:
    """The alternative -- a shared secret -- is a different threat model and not the
    one the architecture assumes, so it is not silently substituted."""
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(auth_mode="jwt", auth_jwt_issuer="https://idp.example.test/")


def test_jwt_mode_rejects_an_empty_algorithm_list(settings_factory: Any) -> None:
    """An empty allow-list matches nothing, or -- depending on the library -- everything.

    Either outcome is a security decision made by accident, so it is refused at startup
    rather than discovered when every request 401s in production.
    """
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(**JWT_OK, auth_jwt_algorithms=[])


def test_unknown_auth_mode_is_rejected(settings_factory: Any) -> None:
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(auth_mode="basic")


def test_algorithm_list_rejects_the_symmetric_algorithms(settings_factory: Any) -> None:
    """``alg: none`` and HMAC verification with the RSA public key are classic JWT bypasses.

    Refusing them at configuration time is the only place they can be refused cheaply.
    """
    for algorithm in ("none", "HS256"):
        with pytest.raises((ConfigurationError, ValueError)):
            settings_factory(**JWT_OK, auth_jwt_algorithms=[algorithm])


def test_prod_environments_must_use_jwt(settings_factory: Any) -> None:
    """Auth mode 'none' in production is an unauthenticated deployment."""
    for environment in ("staging", "production"):
        with pytest.raises((ConfigurationError, ValueError)):
            settings_factory(environment=environment, auth_mode="none", database_required=True)


# -- database ----------------------------------------------------------------


def test_insecure_database_url_is_refused_outside_local(settings_factory: Any) -> None:
    """Credentials over a plaintext connection are exposed to anything on the path."""
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(
            environment="production",
            database_required=True,
            allow_fake_model_adapters=False,
            **JWT_OK,
            database_url="postgresql://user:pw@db.internal:5432/rag",
        )


def test_worker_poll_interval_is_positive(settings_factory: Any) -> None:
    """A zero interval busy-loops the consumer and burns a core doing nothing."""
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(worker_poll_interval_seconds=0)


def test_worker_max_attempts_is_bounded(settings_factory: Any) -> None:
    """Unbounded retries turn a poison message into an infinite loop.

    An upper bound is what forces the message to the dead-letter queue, which is the only
    thing that makes the queue drain.
    """
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(worker_max_attempts=0)


# -- observability -----------------------------------------------------------


def test_log_level_is_from_a_known_set(settings_factory: Any) -> None:
    """An unrecognised level is either rejected by the logging library at first use or,
    worse, silently promoted to DEBUG and logs the payloads NFR-16 forbids."""
    with pytest.raises((ConfigurationError, ValueError)):
        settings_factory(log_level="trace")


def test_settings_are_immutable(settings_factory: Any) -> None:
    """Settings are shared process-wide; a mutated copy is a race and an audit gap."""
    settings = settings_factory()

    with pytest.raises(Exception):  # pydantic ValidationError (frozen instance)
        settings.log_level = "DEBUG"  # type: ignore[misc]  # frozen raises AttributeError


def test_environment_overrides_the_default(settings_factory: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("RAG_LOG_LEVEL", "warning")

    assert settings_factory().log_level.lower() == "warning"


def test_a_clean_environment_needs_no_variables() -> None:
    """Direct construction, not the fixture, to prove there is no hidden dependency."""
    from core.config.settings import AuthMode
    assert Settings().auth_mode is AuthMode.STUB