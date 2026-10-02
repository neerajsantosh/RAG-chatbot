"""Adapter resolution.

Configuration names a model; this maps that name to an adapter. Two rules:

* **No silent fallback.** An unrecognised name raises, listing what is registered. A
  system that quietly substitutes a different model than the one configured would make
  every cost, latency and quality figure on a trace a lie (NFR-13, D10).
* **Fakes cannot reach a deployed environment.** The registry refuses to resolve a ``fake``
  adapter when settings say it is not permitted, so the failure is a startup error rather
  than a production incident.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from core.config.settings import Settings
from core.errors import ConfigurationError
from llm.adapters.fake_chat import FakeChatModel
from llm.adapters.fake_embedder import FakeEmbedder
from llm.adapters.fake_reranker import FakeReranker
from llm.ports import ChatModel, Embedder, Reranker

__all__ = [
    "FAKE_CHAT_NAME",
    "FAKE_EMBED_NAME",
    "FAKE_RERANK_NAME",
    "register_chat",
    "register_embedder",
    "register_reranker",
    "registered_chat_names",
    "registered_embedder_names",
    "registered_reranker_names",
    "reset_registry",
    "resolve_chat",
    "resolve_embedder",
    "resolve_reranker",
]

FAKE_CHAT_NAME: Final = "fake"
FAKE_EMBED_NAME: Final = "fake"
FAKE_RERANK_NAME: Final = "fake"

_CHAT_FACTORIES: dict[str, Callable[[Settings], ChatModel]] = {}
_EMBED_FACTORIES: dict[str, Callable[[Settings], Embedder]] = {}
_RERANK_FACTORIES: dict[str, Callable[[Settings], Reranker]] = {}

_DEFAULT_CHAT_FACTORY: Final = _CHAT_FACTORIES.setdefault(
    FAKE_CHAT_NAME,
    lambda settings: FakeChatModel(
        name=FAKE_CHAT_NAME,
        latency_ms=settings.fake_chat_latency_ms,
    ),
)

_DEFAULT_EMBED_FACTORY: Final = _EMBED_FACTORIES.setdefault(
    FAKE_EMBED_NAME,
    lambda settings: FakeEmbedder(
        dimensions=settings.fake_embedding_dimensions,
        model_version=settings.embedding_model_version,
        batch_size=settings.embedding_batch_size,
        name=FAKE_EMBED_NAME,
    ),
)

_DEFAULT_RERANK_FACTORY: Final = _RERANK_FACTORIES.setdefault(
    FAKE_RERANK_NAME,
    lambda settings: FakeReranker(name=FAKE_RERANK_NAME),
)


def register_chat(name: str, factory: Callable[[Settings], ChatModel]) -> None:
    """Register a chat adapter factory. Phase 3 adds ``hosted`` here."""
    _CHAT_FACTORIES[name] = factory


def register_embedder(name: str, factory: Callable[[Settings], Embedder]) -> None:
    _EMBED_FACTORIES[name] = factory


def register_reranker(name: str, factory: Callable[[Settings], Reranker]) -> None:
    _RERANK_FACTORIES[name] = factory


def registered_chat_names() -> tuple[str, ...]:
    return tuple(sorted(_CHAT_FACTORIES))


def registered_embedder_names() -> tuple[str, ...]:
    return tuple(sorted(_EMBED_FACTORIES))


def registered_reranker_names() -> tuple[str, ...]:
    return tuple(sorted(_RERANK_FACTORIES))


def _unknown(kind: str, name: str, available: tuple[str, ...]) -> ConfigurationError:
    return ConfigurationError(
        f"no {kind} adapter registered under the name {name!r}; registered: {', '.join(available)}",
        code="unknown_model_adapter",
        details={
            "configured": name,
            "registered": list(available),
            "hint": (
                "the 'hosted' adapters land in implementation phase 3; "
                "use CHAT_MODEL=fake for local development"
            ),
        },
    )


def _reject_fake_in_deployment(kind: str, name: str, settings: Settings) -> None:
    if name == FAKE_CHAT_NAME and not settings.allow_fake_model_adapters:
        raise ConfigurationError(
            f"refusing to resolve the fake {kind} adapter: "
            f"ALLOW_FAKE_MODEL_ADAPTERS=false but {kind.upper()}_MODEL={name!r}",
            code="fake_adapter_in_deployment",
            details={"configured": name, "environment": settings.environment},
        )


def resolve_chat(name: str, settings: Settings) -> ChatModel:
    factory = _CHAT_FACTORIES.get(name)
    if factory is None:
        raise _unknown("chat", name, registered_chat_names())
    _reject_fake_in_deployment("chat", name, settings)
    return factory(settings)


def resolve_embedder(name: str, settings: Settings) -> Embedder:
    factory = _EMBED_FACTORIES.get(name)
    if factory is None:
        raise _unknown("embedding", name, registered_embedder_names())
    _reject_fake_in_deployment("embedding", name, settings)
    return factory(settings)


def resolve_reranker(name: str, settings: Settings) -> Reranker:
    factory = _RERANK_FACTORIES.get(name)
    if factory is None:
        raise _unknown("reranker", name, registered_reranker_names())
    _reject_fake_in_deployment("reranker", name, settings)
    return factory(settings)


def reset_registry() -> None:
    """Restore the built-in fake adapters. Tests that register throwaway adapters call this."""
    _CHAT_FACTORIES.clear()
    _CHAT_FACTORIES[FAKE_CHAT_NAME] = _DEFAULT_CHAT_FACTORY
    _EMBED_FACTORIES.clear()
    _EMBED_FACTORIES[FAKE_EMBED_NAME] = _DEFAULT_EMBED_FACTORY
    _RERANK_FACTORIES.clear()
    _RERANK_FACTORIES[FAKE_RERANK_NAME] = _DEFAULT_RERANK_FACTORY
