"""Typed, validated application settings.

Settings are read from the environment (and optionally ``.env``) exactly once, validated
at import time, and cached. Every consumer takes :class:`Settings` as an argument rather
than reading the environment itself, which is what makes the rest of the codebase
testable without environment manipulation.

Two rules are enforced here rather than left to review:

* **No secrets in a plain string.** Credential-shaped settings are ``SecretStr``, so a
  stray ``repr()`` or a settings dump cannot leak one (NFR-14).
* **Non-local environments cannot run weakened.** A staging or production deployment
  with the stub identity provider, the fake model adapters, or an optional database is
  refused at startup. These are the settings that make Phase 1 safe to develop against
  and Phase 1 unsafe to ship.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.errors import ConfigurationError

__all__ = [
    "AuthMode",
    "Environment",
    "LogFormat",
    "Settings",
    "get_settings",
    "reset_settings_cache",
]


class Environment(StrEnum):
    """Deployment environment. Drives the safety validations below."""

    LOCAL = "local"
    CI = "ci"
    STAGING = "staging"
    PROD = "prod"


class AuthMode(StrEnum):
    """How the API establishes who the caller is (FR-29)."""

    STUB = "stub"
    """Accepts a fixed development principal. Local and CI only; refused elsewhere."""

    JWT = "jwt"
    """Verifies a bearer token issued by the configured identity provider."""


class LogFormat(StrEnum):
    JSON = "json"
    TEXT = "text"


def _split_csv(value: object) -> list[str]:
    """Parse a comma-separated setting into a list of non-empty, trimmed values."""
    if isinstance(value, (list, tuple)):
        raw = [str(item) for item in value]
    else:
        raw = str(value or "").split(",")
    return [item.strip() for item in raw if item.strip()]


class Settings(BaseSettings):
    """The full configuration surface. See ``.env.example`` for documentation of each key."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    # -- runtime ------------------------------------------------------------
    environment: Environment = Environment.LOCAL
    allow_fake_model_adapters: bool = True
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON

    # -- API ----------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # -- identity (FR-29) ---------------------------------------------------
    auth_mode: AuthMode = AuthMode.STUB
    auth_jwt_issuer: str = ""
    auth_jwt_audience: str = "rag-chatbot"
    auth_jwt_jwks_url: str = ""
    auth_jwt_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    auth_operator_groups: list[str] = Field(default_factory=lambda: ["rag-operators"])
    auth_admin_groups: list[str] = Field(default_factory=lambda: ["rag-admins"])
    auth_stub_user_id: str = "usr_local_developer"
    auth_stub_groups: list[str] = Field(default_factory=lambda: ["rag-operators", "rag-admins"])

    # -- database -----------------------------------------------------------
    database_url: SecretStr = SecretStr("postgresql://rag:rag@localhost:5432/rag")
    database_pool_min_size: int = Field(default=1, ge=0)
    database_pool_max_size: int = Field(default=10, ge=1)
    database_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    database_probe_timeout_seconds: float = Field(default=1.0, gt=0, le=30.0)
    """Bound on a ``/readyz`` probe, per address.

    Kept short and separate from the connect timeout: a readiness probe that can take as
    long as a connection attempt will itself time out against the orchestrator, and a slow
    readiness endpoint looks like an unhealthy one. Note that ``connect_timeout`` applies per
    resolved address, so a ``localhost`` DSN that yields both ``::1`` and ``127.0.0.1`` can
    take up to twice this. One second keeps the worst case inside a typical probe budget."""
    database_required: bool = False
    """Phase 1 only: lets the API start and serve /healthz without a database.

    Phase 3 flips this once retrieval genuinely requires storage.
    """

    # -- object store and queue (phase 2) -----------------------------------
    object_store_endpoint: str = ""
    object_store_bucket: str = "rag-corpus"
    object_store_access_key: SecretStr = SecretStr("")
    object_store_secret_key: SecretStr = SecretStr("")

    queue_url: SecretStr = SecretStr("")
    queue_name: str = "rag-jobs"
    worker_poll_interval_seconds: float = Field(default=1.0, gt=0, le=60.0)
    """Sleep between empty polls. Kept short because the sleep is interruptible, so a stop
    request does not have to wait it out."""
    worker_max_attempts: int = Field(default=5, ge=1, le=100)
    """Retries before a job is dead-lettered. A placeholder to be tuned against the real
    failure distribution in phase 2; the point in phase 1 is that it is bounded."""

    # -- models (NFR-18) ----------------------------------------------------
    chat_model: str = "fake"
    embedding_model: str = "fake"
    reranker_model: str = "fake"
    """Adapter names resolved by llm.adapters.registry. ``fake`` is the only adapter
    implemented in phase 1; ``hosted`` arrives in phase 3 (implementation.md 5.3). An
    unregistered name is a startup error, never a silent fallback."""
    embedding_model_version: str = "unassigned"
    """Part of ``content_hash``. Phase 2 must not ship with this left as ``unassigned``."""
    embedding_dimensions: int = Field(default=1024, ge=8)
    embedding_batch_size: int = Field(default=64, ge=1)

    hosted_provider_base_url: str = ""
    hosted_provider_api_key: SecretStr = SecretStr("")
    hosted_provider_no_training: bool = True
    """FR-43. Asserted by a test in phase 4, not trusted blindly."""

    fake_embedding_dimensions: int = Field(default=1024, ge=8)
    fake_chat_latency_ms: int = Field(default=0, ge=0)

    # -- cost (NFR-19) ------------------------------------------------------
    cost_budget_per_answer_usd: float = Field(default=0.02, gt=0)
    cost_alert_per_answer_usd: float = Field(default=0.02, gt=0)

    # -- evaluation ---------------------------------------------------------
    evals_dir: Path = Path("evals")
    evals_baseline_dir: Path = Path("evals/baselines")
    eval_judge_enabled: bool = False
    """LLM-as-judge is off by default: it costs money and is non-deterministic."""

    # -- validators ---------------------------------------------------------

    @field_validator("api_cors_origins", "auth_jwt_algorithms", mode="before")
    @classmethod
    def _parse_csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("auth_operator_groups", "auth_admin_groups", "auth_stub_groups", mode="before")
    @classmethod
    def _parse_group_csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        normalised = value.upper()
        if normalised not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}, got {value!r}")
        return normalised

    @field_validator("evals_dir", "evals_baseline_dir", mode="before")
    @classmethod
    def _coerce_path(cls, value: object) -> object:
        return Path(str(value))

    @field_validator("auth_jwt_algorithms")
    @classmethod
    def _validate_jwt_algorithms(cls, value: list[str]) -> list[str]:
        """An empty algorithm list means "verify nothing", which must never start.

        Without this, ``jwt.decode(algorithms=[])`` refuses every token and the deployment
        looks like an identity-provider outage instead of a configuration error. The
        verifier raises as well; this makes the mistake a startup failure.
        """
        if not value:
            raise ValueError(
                "AUTH_JWT_ALGORITHMS must not be empty; refusing to start with a verifier "
                "that accepts no algorithm"
            )
        # Reject symmetric algorithms that are classic JWT bypasses.
        # The architecture only supports RS256 with a JWKS endpoint.
        normalized = [a.upper() for a in value]
        if "NONE" in normalized or "HS256" in normalized:
            raise ValueError(
                "AUTH_JWT_ALGORITHMS must not contain symmetric algorithms (none, HS256); "
                "use RS256 with a JWKS endpoint."
            )
        return value

    @model_validator(mode="after")
    def _validate_unsafe_combinations(self) -> Settings:
        """Refuse configurations that are fine locally but unacceptable deployed.

        These are the shortcuts that make Phase 1 cheap: a stub identity provider, fake
        models, and an optional database. Each is individually defensible in
        development and collectively unacceptable in staging or production.
        """
        problems: list[str] = []

        if self.environment not in (Environment.LOCAL, Environment.CI):
            if self.auth_mode is not AuthMode.JWT:
                problems.append(
                    f"environment={self.environment} requires AUTH_MODE=jwt, got {self.auth_mode}"
                )
            if self.allow_fake_model_adapters:
                problems.append(
                    f"environment={self.environment} requires ALLOW_FAKE_MODEL_ADAPTERS=false"
                )
            if not self.database_required:
                problems.append(f"environment={self.environment} requires DATABASE_REQUIRED=true")

        if self.auth_mode is AuthMode.JWT:
            if not self.auth_jwt_issuer:
                problems.append("AUTH_MODE=jwt requires AUTH_JWT_ISSUER")
            if not self.auth_jwt_jwks_url:
                problems.append("AUTH_MODE=jwt requires AUTH_JWT_JWKS_URL")

        if self.cost_alert_per_answer_usd > self.cost_budget_per_answer_usd:
            problems.append(
                "COST_ALERT_PER_ANSWER_USD must not exceed COST_BUDGET_PER_ANSWER_USD"
            )

        if problems:
            raise ValueError("unsafe configuration: " + "; ".join(problems))

        return self

    # -- derived helpers ----------------------------------------------------

    @property
    def is_local(self) -> bool:
        return self.environment in (Environment.LOCAL, Environment.CI)

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PROD

    def require_local(self, feature: str) -> None:
        """Guard a development-only feature. Raises outside local and CI."""
        if not self.is_local:
            raise ConfigurationError(
                f"{feature} is only permitted in local and CI environments, "
                f"but ENVIRONMENT={self.environment}",
                code="unsafe_configuration",
            )

    def safe_dump(self) -> dict[str, str]:
        """A dict safe to log: every secret rendered as ``***``.

        Used by the startup banner and the ``/readyz`` payload. Never log
        :meth:`model_dump` directly.
        """
        raw = self.model_dump(mode="json")
        redacted: dict[str, str] = {}
        for key, value in raw.items():
            text = str(value)
            redacted[key] = "***" if isinstance(getattr(self, key, None), SecretStr) else text
        return redacted


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings, raising :class:`ConfigurationError` on bad input.

    ``ConfigurationError`` rather than pydantic's own error type, so that a
    misconfiguration is reported the same way as every other operational problem.
    """
    try:
        return Settings()
    except Exception as exc:
        raise ConfigurationError(
            f"invalid configuration: {exc}",
            code="invalid_configuration",
            details={"hint": "check .env against .env.example"},
        ) from exc


def reset_settings_cache() -> None:
    """Clear the cached settings. Tests call this after mutating the environment."""
    get_settings.cache_clear()
