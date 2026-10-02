"""Per-token pricing and cost estimation.

NFR-19 requires cost to be tracked per answer, and architecture D10 requires it to be
computed from the actual token counts on each call rather than from a volume average.
Averages hide exactly the cases worth noticing: a prompt that grew, a retrieval setting
that started returning twice as many chunks, a reranker running on a hot path.

An unknown model therefore raises rather than defaulting to zero. A silent zero is
indistinguishable from a genuinely free call, which is how a cost budget quietly stops
meaning anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from core.errors import ConfigurationError
from llm.ports import Usage

__all__ = [
    "MILLION",
    "ModelPricing",
    "estimate_cost",
    "pricing_for",
    "register_pricing",
]

MILLION: Final = 1_000_000


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Cost per million tokens, in USD."""

    model: str
    input_per_million: float
    output_per_million: float

    def cost_for(self, usage: Usage) -> float:
        """Cost of one call. Rounded to micro-dollars to avoid float noise in the DB."""
        input_cost = (usage.tokens_in / MILLION) * self.input_per_million
        output_cost = (usage.tokens_out / MILLION) * self.output_per_million
        return round(input_cost + output_cost, 8)

    def describe(self) -> dict[str, float | str]:
        return {
            "model": self.model,
            "input_per_million": self.input_per_million,
            "output_per_million": self.output_per_million,
        }


_PRICING: dict[str, ModelPricing] = {}


def register_pricing(pricing: ModelPricing) -> None:
    _PRICING[pricing.model] = pricing


def pricing_for(model: str) -> ModelPricing:
    """Return pricing for ``model``, raising when it is not registered."""
    found = _PRICING.get(model)
    if found is None:
        raise ConfigurationError(
            f"no pricing registered for model {model!r}; "
            "register it before serving so cost can be attributed",
            code="missing_pricing",
            details={"model": model, "registered": sorted(_PRICING)},
        )
    return found


def estimate_cost(model: str, usage: Usage) -> float:
    """Cost of one call to ``model`` for the given usage."""
    return pricing_for(model).cost_for(usage)


def zero_pricing(*models: str) -> None:
    """Register models that genuinely cost nothing, such as the offline fakes.

    Explicit and greppable, so a reader can see at a glance which models have no billing
    attached -- which is exactly the question a reader of a trace should be able to answer.
    """
    for model in models:
        register_pricing(ModelPricing(model=model, input_per_million=0.0, output_per_million=0.0))


zero_pricing("fake", "fake-chat", "fake-rerank", "local-embed")
