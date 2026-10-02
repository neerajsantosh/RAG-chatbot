"""Phase 1 API acceptance gates.

These mirror the plan's verification table:

* ``/healthz`` answers 200 with a non-empty service identifier, **without a database**.
* ``/readyz`` answers 503 when the database is down. The 200 case needs a live database and
  is covered by ``tests/integration/test_readyz_with_database.py`` behind ``requires_db``.

The 503 assertion is the one that earns its keep. A readiness endpoint that always returns
200 passes every liveness smoke test and tells an orchestrator nothing; proving it degrades
is what makes the check real.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from core.config.settings import AuthMode, Settings


@pytest.fixture
def client(settings_factory: Any) -> Iterator[TestClient]:
    """A stub-auth client. Every non-health route authenticates, so stub mode is what makes
    the 401 tests meaningful -- in JWT mode nothing is ever reachable without a token."""
    settings: Settings = settings_factory(
        auth_mode=AuthMode.STUB,
        # Long enough that the probe cannot itself be the reason for a 503 being slow.
        database_probe_timeout_seconds=0.2,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


def test_healthz_is_200_without_a_database(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["service"], "the plan requires a non-empty service identifier"
    assert body["status"] == "ok"


def test_healthz_echoes_a_request_id(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.headers.get("X-Request-Id"), "every response must be correlatable"


def test_healthz_accepts_a_well_formed_inbound_request_id(client: TestClient) -> None:
    """A valid inbound id is reused so a trace spans services."""
    response = client.get("/healthz", headers={"X-Request-Id": "req_from_upstream_01"})

    assert response.headers["X-Request-Id"] == "req_from_upstream_01"


@pytest.mark.parametrize(
    "hostile",
    [
        "bad id with spaces",
        "id\nwith-newline",
        "id\x00with-null-byte",
        "tab\tseparated",
        "x" * 200,
        "",
    ],
)
def test_healthz_rejects_a_hostile_inbound_request_id(client: TestClient, hostile: str) -> None:
    """Unvalidated echoing is a log-injection vector.

    The id is written to every log line for the request, so a caller that could smuggle a
    newline would be able to forge log entries.
    """
    response = client.get("/healthz", headers={"X-Request-Id": hostile})

    echoed = response.headers.get("X-Request-Id", "")
    assert "\n" not in echoed and "\r" not in echoed and "\x00" not in echoed
    assert echoed != hostile, f"hostile id {hostile!r} was echoed back verbatim"
    assert echoed.startswith("req_")


def test_readyz_is_503_when_the_database_is_unreachable(client: TestClient) -> None:
    """The failure case, which is the one that proves the check is real."""
    response = client.get("/readyz")

    assert response.status_code == 503, (
        "readyz must report 503 when PostgreSQL does not answer, even with "
        "DATABASE_REQUIRED=false -- otherwise the readiness probe is a constant 200"
    )


def test_readyz_reports_which_dependency_failed(client: TestClient) -> None:
    body = client.get("/readyz").json()

    assert body["ready"] is False
    assert body["environment"] == "local"
    assert body["dependencies"], "a failure with no named dependency is unactionable"
    failed = [d for d in body["dependencies"] if not d["reachable"]]
    assert failed, "readyz reported not-ready without naming a failing dependency"
    assert any("postgres" in d["name"] for d in failed)
    assert all(d["detail"] for d in failed), "a failed dependency should say why"


def test_readyz_respects_the_probe_timeout(client: TestClient) -> None:
    """The probe is bounded, so a hung database cannot hang the endpoint."""
    settings_deadline = 0.2
    import time

    started = time.perf_counter()
    client.get("/readyz")
    elapsed = time.perf_counter() - started

    # Generous upper bound: the point is that it returns at all, well under the 5s connect
    # timeout a naive probe would wait for.
    assert elapsed < settings_deadline + 3.0, (
        f"readyz took {elapsed:.2f}s; the probe should be bounded by its own timeout"
    )


def test_version_reports_build_metadata(client: TestClient) -> None:
    body = client.get("/version").json()

    assert body["version"]
    assert body["service"]
    assert body["phase"]


def test_liveness_and_readiness_do_not_require_a_principal(client: TestClient) -> None:
    """Probes must work with no credential, or a failing identity provider looks like a
    failing database and gets remediated as one."""
    for path in ("/healthz", "/readyz", "/version"):
        assert client.get(path).status_code in (200, 503), path


def test_response_time_header_is_present(client: TestClient) -> None:
    assert client.get("/healthz").headers.get("X-Response-Time-Ms")


def test_cors_headers_are_present_for_a_configured_origin(settings_factory: Any) -> None:
    settings = settings_factory(api_cors_origins=["http://localhost:3000"])
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        response = test_client.get("/healthz", headers={"Origin": "http://localhost:3000"})

    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_does_not_allow_an_unconfigured_origin(settings_factory: Any) -> None:
    """Wildcard CORS on a credentialed API is a data leak, not a convenience."""
    settings = settings_factory(api_cors_origins=["http://localhost:3000"])
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        response = test_client.get("/healthz", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers
