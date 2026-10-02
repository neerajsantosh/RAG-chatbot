"""Deterministic adapters.

These exist so the entire application runs and tests offline with no provider account
and no cost. That is not a convenience: the Phase 1 gate requires the whole system to run
end to end on fakes, and every later phase's test suite inherits that property.

Determinism is the point. The gate requires "run the suite twice, identical results", so
nothing here may use Python's randomised ``hash()``, wall-clock time, or iteration over
unordered sets. Embeddings derive from ``sha256``; the chat adapter derives from its own
input.

:func:`llm.adapters.registry.assert_not_fake_in_production` is the guard that stops a fake
reaching a deployed environment.
"""

from llm.adapters.fake_chat import FakeChatModel
from llm.adapters.fake_embedder import FakeEmbedder
from llm.adapters.fake_reranker import FakeReranker
from llm.adapters.hosted.hosted_chat import HostedChatModel
from llm.adapters.hosted.hosted_embedder import HostedEmbedder
from llm.adapters.hosted.hosted_reranker import HostedReranker

__all__ = [
    "FakeChatModel",
    "FakeEmbedder",
    "FakeReranker",
    "HostedChatModel",
    "HostedEmbedder",
    "HostedReranker",
]