"""Application factory.

Everything about how the app starts is decided here, in one readable place, because the
alternatives -- module-level singletons and side effects at import time -- are what make a
FastAPI codebase hard to test. ``create_app()`` takes its dependencies as arguments and can
be called more than once in a process, which is what lets the test suite stand up an app
with a fake model adapter and an unreachable database.

Two things happen here that are easy to overlook:

* **The startup banner logs the configuration through** :meth:`Settings.safe_dump`, so every
  credential is masked. It is the first thing printed on boot and it would otherwise be a
  convenient place to leak ``DATABASE_URL``.
* **CORS is restricted to configured origins.** Wildcard CORS on a cookie-authenticated API
  is a cross-origin data leak; the default is a single localhost origin, and phase 4
  replaces it with the real deployment origins.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import install_exception_handlers
from api.middleware import (
    AuthMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
    TimingMiddleware,
)
from api.middleware.auth import build_authenticator
from api.middleware.ratelimit import UnenforcedLimiter
from api.routes import (
    admin,
    chat,
    conversations,
    feedback,
    health,
    query,
    sources,
    traces,
)
from core.config.settings import Settings, get_settings
from core.logging import configure_logging, get_logger, log_extra
from core.telemetry import reset_recorder

__all__ = ["API_TITLE", "ROUTERS", "create_app"]

_logger = get_logger(__name__)

API_TITLE = "RAG Chatbot API"
API_DESCRIPTION = (
    "Retrieval-augmented answers over an internal document corpus, with access control "
    "enforced on every read. Phase 1: the full route surface is registered and typed, "
    "but reads return empty collections and writes return 501."
)

#: Registered in this order. Health first so the probes are found before the rest, and
#: admin last because it is the only router that inspects roles.
ROUTERS = (
    health.router,
    conversations.router,
    chat.router,
    query.router,
    sources.router,
    traces.router,
    feedback.router,
    admin.router,
)


def _log_startup_banner(settings: Settings) -> None:
    """Print the effective configuration, with every secret masked.

    Also states plainly which development shortcuts are active. A staging instance that is
    silently running the fake model adapters is the kind of thing nobody notices until an
    answer quality review, and this line is the cheapest possible place to prevent it.
    """
    _logger.info(
        "starting service",
        extra=log_extra(
            service="rag-api",
            environment=str(settings.environment),
            auth_mode=str(settings.auth_mode),
            chat_model=settings.chat_model,
            embedding_model=settings.embedding_model,
            allow_fake_model_adapters=settings.allow_fake_model_adapters,
            database_required=settings.database_required,
            log_format=str(settings.log_format),
        ),
    )

    if settings.allow_fake_model_adapters:
        _logger.warning(
            "fake model adapters are permitted; answers in this process are not real"
        )
    if settings.auth_mode.value == "stub":
        _logger.warning(
            "stub authentication is active; every caller is the configured development user"
        )

    # safe_dump, never model_dump: this is the line that keeps DATABASE_URL and the
    # provider API key out of the boot log (NFR-14).
    _logger.debug("effective configuration", extra=log_extra(**settings.safe_dump()))


def _assert_safe_configuration(settings: Settings) -> None:
    """Refuse to serve traffic from an unsafe configuration.

    Settings validation already rejects these combinations, so reaching here means the
    process was configured by some other route. It is cheap to check again before answering
    a single request.
    """
    if settings.is_production and (
        settings.allow_fake_model_adapters or not settings.database_required
    ):
        raise RuntimeError(
            "refusing to start: production requires real model adapters and a required database"
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Callable more than once per process."""
    active = settings or get_settings()

    configure_logging(level=active.log_level, fmt=str(active.log_format))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _assert_safe_configuration(active)
        _log_startup_banner(active)
        yield
        # Recorder state is process-wide; clearing it on shutdown keeps a test that
        # restarts the app from seeing spans from the previous instance.
        reset_recorder()

    app = FastAPI(
        title=API_TITLE,
        description=API_DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
        # The interactive docs expose the full route surface. Harmless for a local stub
        # identity, but phase 4 disables them outside local environments -- the schemas
        # describe how to reach the corpus.
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # Starlette runs the most recently added middleware first, so the effective per-request
    # order is the reverse of the reading order of this block. The resolved sequence is
    # asserted by tests/unit/test_api_middleware_order.py rather than trusted by inspection.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active.api_cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    )
    # Rate limiting is keyed on the principal, so auth must run before it. Added first
    # here, which under Starlette's reverse-execution rule makes it the innermost of the
    # three -- after auth, before the handler. See api.middleware.MIDDLEWARE_ORDER.
    app.add_middleware(RateLimitMiddleware, limiter=UnenforcedLimiter(), enforce=False)
    app.add_middleware(AuthMiddleware, authenticator=build_authenticator(active))
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    install_exception_handlers(app)
    for router in ROUTERS:
        app.include_router(router)

    return app
