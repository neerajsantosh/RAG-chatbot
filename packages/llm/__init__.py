"""Model provider abstraction.

Everything the application knows about a language model lives behind three ports in
:mod:`llm.ports`: ``ChatModel``, ``Embedder`` and ``Reranker``. This is the structural
expression of NFR-18 -- swappable providers -- and it is enforced rather than merely
intended: ``tests/test_dependency_rules.py`` fails the build if a provider SDK is imported
anywhere outside :mod:`llm.adapters`.

Phase 1 ships only the deterministic fake adapters. Real hosted adapters land in phase 3
(see ``docs/implementation.md`` §5.3), at which point the rest of the system needs no
change, because it never referenced a provider to begin with.
"""

from llm.ports import ChatModel, Embedder, Message, ModelCapabilities, Reranker, Usage
from llm.pricing import ModelPricing, estimate_cost

__all__ = [
    "ChatModel",
    "Embedder",
    "Message",
    "ModelCapabilities",
    "ModelPricing",
    "Reranker",
    "Usage",
    "estimate_cost",
]
