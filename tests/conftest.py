"""Shared fixtures.

Two things are established here that the rest of the suite depends on:

**Settings are built explicitly, never read from the developer's environment.** A test that
inherits ``DATABASE_URL`` or ``AUTH_MODE`` from a shell is a test that passes on one machine
and fails on another. ``settings_factory`` builds a :class:`Settings` from scratch, and the
one autouse fixture that patches the environment exists to make an inherited variable
*visible* rather than to paper over it.

**No test needs a database or a network.** Everything in phase 1 is offline and
deterministic; the ``requires_db`` and ``requires_network`` markers exist for phase 2, and
:func:`require_database` skips cleanly when the instance is not reachable. A suite that
fails because a developer has not started Docker yet is a suite people stop running.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from core.config.settings import AuthMode, Settings
from core.telemetry import reset_recorder

__all__ = [
    "SettingsFactory",
    "corpus_documents",
    "database_url",
    "golden_dataset_path",
    "repo_root",
    "require_database",
    "settings_factory",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "tests" / "fixtures" / "corpus"
GOLDEN_MINI = REPO_ROOT / "tests" / "fixtures" / "golden" / "mini.jsonl"

SettingsFactory = Callable[..., Settings]

#: Environment variables the suite must not inherit. Listed explicitly rather than by
#: scanning every Settings field: a scan would also clear variables a developer set on
#: purpose for a manual run, and this list is the set that actually changes test meaning.
_INHERITED_ENV_KEYS = (
    "AUTH_MODE",
    "AUTH_JWT_ISSUER",
    "AUTH_JWT_JWKS_URL",
    "AUTH_JWT_AUDIENCE",
    "AUTH_JWT_ALGORITHMS",
    "ALLOW_FAKE_MODEL_ADAPTERS",
    "ENVIRONMENT",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "CHAT_MODEL",
    "EMBEDDING_MODEL",
    "RERANKER_MODEL",
    "DATABASE_REQUIRED",
    "DATABASE_URL",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove inherited configuration so every test starts from the defaults.

    Autouse, and deliberately so: a test that needs a specific value sets it, and a test
    that does not cannot be steered by whatever is in the shell.
    """
    for key in _INHERITED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # The span recorder is process-wide state; without this, a test that asserts on spans
    # sees spans recorded by whichever test happened to run before it.
    reset_recorder()


@pytest.fixture
def settings_factory() -> SettingsFactory:
    """Build a :class:`Settings` with explicit overrides.

    Not cached, and deliberately not reading the environment: each call is an independent
    object, so mutating one in a test cannot leak into the next.

    Overrides are merged into the base kwargs and passed to the constructor rather than
    applied with ``dataclasses.replace`` -- ``Settings`` is a ``BaseSettings``, not a
    dataclass, and ``replace`` raises on it.
    """

    def _make(**overrides: Any) -> Settings:
        kwargs: dict[str, Any] = {
            "environment": "local",
            "allow_fake_model_adapters": True,
            "auth_mode": AuthMode.STUB,
            "database_required": False,
            "log_level": "WARNING",
            "log_format": "json",
        }
        kwargs.update(overrides)
        return Settings(**kwargs)

    return _make


@pytest.fixture
def settings(settings_factory: SettingsFactory) -> Settings:
    """Default local/test settings."""
    return settings_factory()


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def golden_dataset_path() -> Path:
    assert GOLDEN_MINI.exists(), f"missing golden fixture: {GOLDEN_MINI}"
    return GOLDEN_MINI


@pytest.fixture(scope="session")
def corpus_documents() -> list[dict[str, Any]]:
    """The tiny corpus used by wiring tests.

    Documents carry ACL tags and a visibility, because a corpus fixture without them would
    let a test pass that never exercised the field the RLS policies depend on.
    """
    documents: list[dict[str, Any]] = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        import json

        documents.append(json.loads(path.read_text(encoding="utf-8")))
    assert documents, f"no corpus documents found in {CORPUS_DIR}"
    return documents


def database_url() -> str:
    """The database URL for integration tests, from the environment only."""
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")


def require_database() -> str:
    """Return a database URL, or skip the test.

    Skipping rather than failing is the right behaviour here: "PostgreSQL is not running"
    is not a defect in the code under test, and a phase-1 suite that demands a live database
    cannot be run by anyone who has only cloned the repository.
    """
    url = database_url()
    if not url:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL set; skipping database test")
    try:
        import psycopg
    except ImportError:  # pragma: no cover - psycopg is a hard dependency
        pytest.skip("psycopg is not installed")
        raise
    try:
        with psycopg.connect(url, connect_timeout=2):
            pass
    except Exception as exc:  # noqa: BLE001 - any driver error means "not reachable" here
        pytest.skip(f"database is not reachable ({type(exc).__name__}); skipping")
    return url


@pytest.fixture
def db_url() -> Iterator[str]:
    """Session-wide reachability probe, yielded as the URL."""
    yield require_database()
