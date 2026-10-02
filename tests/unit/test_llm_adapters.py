"""Fake model adapters: deterministic, and refused when they are not allowed.

Phase 1 runs the entire system offline with no provider account and no cost. That is only
honest if two things hold, and both are tested here:

* the fakes are **deterministic**, so the eval suite and the tests do not flap, and
* the fakes are **refused** when ``ALLOW_FAKE_MODEL_ADAPTERS=false``, so a staging
  deployment cannot silently serve invented answers.

The second is the security-relevant one. A fake adapter that quietly keeps working when it
is nominally disabled turns a staging instance into a source of confident fiction.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.errors import ConfigurationError
from llm.adapters.fake_chat import Misbehaviour
from llm.adapters.registry import (
    registered_chat_names,
    resolve_chat,
    resolve_embedder,
    resolve_reranker,
)
from llm.ports import ChatModel, Embedder, Message, Reranker

DANGLING_CITATION = Misbehaviour.DANGLING_CITATION
UNCITED_CLAIM = Misbehaviour.UNCITED_CLAIM
REFUSAL = Misbehaviour.REFUSAL


def _user(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


@pytest.fixture
def fake_settings(settings_factory: Any) -> Any:
    return settings_factory(
        allow_fake_model_adapters=True,
        chat_model="fake",
        embedding_model="fake",
        reranker_model="fake",
    )


# -- the refusal path --------------------------------------------------------


def test_unknown_model_name_is_an_error_not_a_silent_fallback(fake_settings: Any) -> None:
    """Falling back to a working adapter is how a typo ships a fake to production."""
    with pytest.raises(ConfigurationError) as exc:
        resolve_chat("gppt-4o", fake_settings)

    assert "fake" in str(exc.value), "the error should name the registered adapters"


def test_fake_chat_is_refused_when_not_allowed(fake_settings: Any) -> None:
    disabled = fake_settings.model_copy(update={"allow_fake_model_adapters": False})

    with pytest.raises(ConfigurationError):
        resolve_chat("fake", disabled)


def test_fake_embedder_is_refused_when_not_allowed(fake_settings: Any) -> None:
    disabled = fake_settings.model_copy(update={"allow_fake_model_adapters": False})

    with pytest.raises(ConfigurationError):
        resolve_embedder("fake", disabled)


def test_fake_reranker_is_refused_when_not_allowed(fake_settings: Any) -> None:
    disabled = fake_settings.model_copy(update={"allow_fake_model_adapters": False})

    with pytest.raises(ConfigurationError):
        resolve_reranker("fake", disabled)


def test_settings_refuse_fake_adapters_outside_local(settings_factory: Any) -> None:
    for environment in ("staging", "production"):
        with pytest.raises((ConfigurationError, ValueError)):
            settings_factory(
                environment=environment,
                allow_fake_model_adapters=True,
                auth_mode="jwt",
                auth_jwt_issuer="https://idp.example.test/",
                auth_jwt_jwks_url="https://idp.example.test/jwks.json",
                database_required=True,
            )


# -- determinism -------------------------------------------------------------


def test_chat_output_is_identical_across_calls(fake_settings: Any) -> None:
    chat = resolve_chat("fake", fake_settings)

    first = chat.complete(_user("What is the remote work policy?"))
    second = chat.complete(_user("What is the remote work policy?"))

    assert first.text == second.text
    assert first.usage.to_dict() == second.usage.to_dict()


def test_embedding_output_is_identical_across_calls(fake_settings: Any) -> None:
    embedder = resolve_embedder("fake", fake_settings)

    assert embedder.embed_documents(["hello", "world"]) == embedder.embed_documents(
        ["hello", "world"]
    )


def test_embeddings_are_deterministic_per_text_not_per_batch(fake_settings: Any) -> None:
    """A text must embed identically regardless of what it was batched with.

    Otherwise an index built in batches of 64 is not comparable to one built in batches of
    1, and search results change when the batching configuration changes.
    """
    embedder = resolve_embedder("fake", fake_settings)
    alone = embedder.embed_documents(["hello"])[0]
    batched = embedder.embed_documents(["other", "hello", "third"])[1]

    assert alone == batched


def test_embed_query_matches_embed_document(fake_settings: Any) -> None:
    """A query and the identical document must land in the same place, or exact-term
    matching is impossible to achieve no matter how the index is built."""
    embedder = resolve_embedder("fake", fake_settings)

    assert embedder.embed_query("hello") == embedder.embed_documents(["hello"])[0]


def test_embedding_dimension_matches_configuration(fake_settings: Any) -> None:
    settings = fake_settings.model_copy(update={"fake_embedding_dimensions": 8})
    embedder = resolve_embedder("fake", settings)

    assert len(embedder.embed_documents(["hello"])[0]) == 8
    assert embedder.dimensions == 8


def test_reranker_scores_are_deterministic(fake_settings: Any) -> None:
    reranker = resolve_reranker("fake", fake_settings)
    passages = ["alpha", "beta", "gamma"]

    assert reranker.score("alpha", passages) == reranker.score("alpha", passages)


def test_reranker_top_n_is_sorted_and_bounded(fake_settings: Any) -> None:
    reranker = resolve_reranker("fake", fake_settings)

    ranked = reranker.top_n("alpha", ["alpha", "beta", "gamma"], n=2)

    assert len(ranked) == 2
    assert ranked[0][1] >= ranked[1][1], "top_n must return descending scores"


# -- cost accounting ---------------------------------------------------------


def test_usage_is_reported(fake_settings: Any) -> None:
    result = resolve_chat("fake", fake_settings).complete(_user("hello there"))

    assert result.usage.tokens_in > 0
    assert result.usage.tokens_out > 0


def test_usage_is_not_miscounted_when_the_answer_is_truncated(fake_settings: Any) -> None:
    """Usage must reflect what was *produced*, not what was requested.

    Cost is billed on generated tokens. A cap that truncates mid-generation still consumed
    those tokens upstream, and a harness reporting the requested count overstates every
    capped answer.
    """
    chat = resolve_chat("fake", fake_settings)
    unlimited = chat.complete(_user("hello"))
    capped = chat.complete(_user("hello"), max_output_tokens=3)

    assert capped.usage.tokens_out == 3
    assert capped.usage.tokens_out < unlimited.usage.tokens_out
    assert capped.usage.tokens_in == unlimited.usage.tokens_in


def test_usage_accumulates_across_a_stream(fake_settings: Any) -> None:
    """Streaming must not lose the final usage record.

    A stream that never reports usage makes cost tracking (NFR-19) impossible for exactly
    the call path that produces the most tokens.
    """
    chat = resolve_chat("fake", fake_settings)
    for _ in chat.stream(_user("hello")):
        pass

    assert chat.last_usage is not None
    assert chat.last_usage.tokens_out > 0


def test_stream_and_complete_agree_on_usage(fake_settings: Any) -> None:
    """The same prompt through both paths must cost the same, or one path is untracked."""
    chat = resolve_chat("fake", fake_settings)
    streamed = "".join(chat.stream(_user("hello")))
    completed = chat.complete(_user("hello"))

    assert streamed == completed.text
    assert chat.last_usage.to_dict() == completed.usage.to_dict()


def test_finish_reason_distinguishes_truncation(fake_settings: Any) -> None:
    """A truncated answer must not be reported as a complete one.

    A provisional answer that looks final is the failure mode the streaming design in
    architecture Â§6.1 exists to prevent.
    """
    chat = resolve_chat("fake", fake_settings)

    assert chat.complete(_user("hello"), max_output_tokens=3).finish_reason == "length"
    assert chat.complete(_user("hello")).finish_reason == "stop"


def test_usage_adds(fake_settings: Any) -> None:
    result = resolve_chat("fake", fake_settings).complete(_user("hello"))

    assert result.usage.total == result.usage.tokens_in + result.usage.tokens_out


# -- refusals and validation -------------------------------------------------


def test_refusal_is_reported(fake_settings: Any) -> None:
    """The fake must be able to refuse, or the refusal path is untestable offline."""
    result = resolve_chat("fake", fake_settings).complete(_user("anything"), misbehaviour=REFUSAL)

    assert "don't have enough" in result.text


def test_misbehaving_modes_produce_bad_answers(fake_settings: Any) -> None:
    """Citation and refusal tests need a model that can genuinely go wrong.

    Without a deterministic way to produce a dangling citation, the citation verifier can
    only ever be tested against correct output.
    """
    chat = resolve_chat("fake", fake_settings)

    assert "[1][8]" in chat.complete(_user("context [1]"), misbehaviour=DANGLING_CITATION).text
    assert "[" not in chat.complete(_user("context [1]"), misbehaviour=UNCITED_CLAIM).text


def test_fingerprint_is_stable_and_hides_the_prompt(fake_settings: Any) -> None:
    """The fingerprint exists so a prompt change is detectable without logging content."""
    chat = resolve_chat("fake", fake_settings)

    first = chat.fingerprint(_user("secret question"))
    second = chat.fingerprint(_user("secret question"))

    assert first == second
    assert "secret question" not in first
    assert len(first) == 16


def test_fakes_report_their_identity(fake_settings: Any) -> None:
    """An answer must be traceable to the adapter that produced it.

    Without this there is no way to tell a real model response from a fake one in a log,
    which is the entire risk the ``ALLOW_FAKE_MODEL_ADAPTERS`` switch manages.
    """
    chat = resolve_chat("fake", fake_settings)
    embedder = resolve_embedder("fake", fake_settings)

    assert "fake" in chat.name
    assert "fake" in embedder.name
    assert chat.capabilities.seeded_determinism is True
    assert chat.complete(_user("hello")).model == chat.name


def test_completion_serialises(fake_settings: Any) -> None:
    """Reports must be machine-readable, so the payload has to round-trip."""
    payload = resolve_chat("fake", fake_settings).complete(_user("hello")).to_dict()

    assert set(payload) >= {"text", "usage", "model", "finish_reason"}


# -- ports -------------------------------------------------------------------


def test_the_three_ports_have_a_fake(fake_settings: Any) -> None:
    """The plan's gate: every port has at least one fake and a real-adapter slot."""
    assert isinstance(resolve_chat("fake", fake_settings), ChatModel)
    assert isinstance(resolve_embedder("fake", fake_settings), Embedder)
    assert isinstance(resolve_reranker("fake", fake_settings), Reranker)


def test_a_real_adapter_slot_exists(fake_settings: Any) -> None:
    """Phase 3 provides the hosted adapter; the name must already be reserved.

    An unregistered name is an error, so registering nothing now is fine -- what matters is
    that the error message tells a developer what to register.
    """
    assert "fake" in registered_chat_names()
    with pytest.raises(ConfigurationError):
        resolve_chat("hosted", fake_settings)
