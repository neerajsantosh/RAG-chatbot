"""Health and readiness.

The two endpoints answer different questions and the difference is the whole design:

* ``/healthz`` -- "is this process alive?" It touches nothing external. It returns 200
  whenever the process can serve HTTP at all, *including when PostgreSQL is unreachable*.
  This is what makes Phase 1 runnable without a database (NFR-9), and it is deliberate:
  a liveness probe that fails when a dependency is down causes the orchestrator to restart
  an application that is working perfectly well.
* ``/readyz`` -- "should this instance receive traffic?" It checks PostgreSQL and returns
  503 when it cannot. Readiness is the honest place to fail, so traffic stops arriving
  while the operator gets a clear reason.

Conflating them is the standard way to turn a database blip into a restart storm.

Neither endpoint is authenticated. That is required -- an orchestrator cannot present a
user token -- and it is safe because both bodies are deliberately free of anything
sensitive. Deployment state (mode, versions, pool size) is not secret; document and question
content obviously is not present. The rule for anything added to these responses later is
that it must survive being readable by anyone who can reach the port.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from api.deps import DatabaseDep, SettingsDep
from core.config.settings import Settings
from storage.db.engine import DatabaseEngine

__all__ = ["HealthResponse", "ReadinessResponse", "router"]

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness. Nothing here depends on anything outside this process."""

    status: str = "ok"
    service: str = "rag-api"
    version: str = Field(default="0.1.0")
    phase: str = "phase-1"
    """Exposed so a staging instance can be identified from outside. Phase 1 adds no
    questions, chunks or documents to this response."""


class DependencyStatus(BaseModel):
    name: str
    reachable: bool
    required: bool
    detail: str = ""


class ReadinessResponse(BaseModel):
    """Readiness. ``ready`` is false when any required dependency is unreachable."""

    status: str
    ready: bool
    environment: str
    auth_mode: str
    allow_fake_model_adapters: bool
    chat_model: str
    embedding_model: str
    dependencies: list[DependencyStatus]

    @classmethod
    def build(cls, settings: Settings, engine: DatabaseEngine) -> ReadinessResponse:
        health = engine.health()
        reachable = bool(health.get("reachable"))

        dependencies = [
            DependencyStatus(
                name=str(health.get("dependency", "postgres")),
                reachable=reachable,
                # Informational only. Startup would fail if the database were mandatory and
                # unreachable, but readiness does not consult this flag: "the database is
                # down" means 503 either way. A deployment that reported itself ready while
                # unable to read the corpus would take traffic it cannot serve, and a
                # constant 200 would make this endpoint untestable (implementation.md 4.6).
                required=bool(health.get("required")),
                detail="" if reachable else "database did not answer a probe query",
            )
        ]

        ready = all(dep.reachable for dep in dependencies)
        return cls(
            status="ready" if ready else "not_ready",
            ready=ready,
            environment=str(settings.environment),
            auth_mode=str(settings.auth_mode),
            allow_fake_model_adapters=settings.allow_fake_model_adapters,
            chat_model=settings.chat_model,
            embedding_model=settings.embedding_model,
            dependencies=dependencies,
        )


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    """Always 200 while the process can serve HTTP. Does not touch PostgreSQL."""
    return HealthResponse()


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={
        503: {"model": ReadinessResponse, "description": "a required dependency is down"}
    },
)
async def readyz(
    response: Response, settings: SettingsDep, engine: DatabaseDep
) -> ReadinessResponse:
    """503 when a required dependency is unreachable. Never authenticated."""
    payload = ReadinessResponse.build(settings, engine)
    if not payload.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


@router.get("/version", include_in_schema=False)
async def version() -> dict[str, Any]:
    """Unauthenticated version stamp. Cheap enough to poll during an incident."""
    return {"service": "rag-api", "version": "0.1.0", "phase": "phase-1"}
