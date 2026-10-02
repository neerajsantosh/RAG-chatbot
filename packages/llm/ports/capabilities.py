"""Capability declarations.

A model that cannot stream, or cannot be told to return JSON, must not be silently used
as though it can. Capabilities are therefore *declared* and the orchestrator branches on
them (architecture §12), so a cheaper or smaller model can be substituted without a
behaviour change nobody noticed until production.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "SUPPORTED_CAPABILITIES",
    "ModelCapabilities",
    "no_capabilities",
    "rich_capabilities",
]

SUPPORTED_CAPABILITIES: Final[tuple[str, ...]] = (
    "streaming",
    "json_mode",
    "tool_calling",
    "system_role",
    "seeded_determinism",
)
"""The capability vocabulary. A capability outside this tuple is a typo, not a feature."""


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """What a given model can actually do."""

    streaming: bool = False
    json_mode: bool = False
    tool_calling: bool = False
    system_role: bool = True
    seeded_determinism: bool = False
    max_context_tokens: int = 8_192
    max_output_tokens: int = 2_048

    def require(self, *names: str) -> None:
        """Raise unless every named capability is available.

        Used at the point of use so the failure names the capability rather than surfacing
        as a malformed provider response.
        """
        available = self.as_dict()
        missing = [name for name in names if not available.get(name, False)]
        if missing:
            raise ValueError(f"model does not support required capabilities: {missing}")

    def as_dict(self) -> dict[str, bool | int]:
        return {
            "streaming": self.streaming,
            "json_mode": self.json_mode,
            "tool_calling": self.tool_calling,
            "system_role": self.system_role,
            "seeded_determinism": self.seeded_determinism,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
        }

    def __contains__(self, name: object) -> bool:
        if name not in SUPPORTED_CAPABILITIES:
            return False
        return bool(self.as_dict().get(str(name), False))


no_capabilities: Final = ModelCapabilities(
    streaming=False,
    json_mode=False,
    tool_calling=False,
    system_role=False,
)
"""The weakest model we will accept. Used by tests that assert capability gating."""

rich_capabilities: Final = ModelCapabilities(
    streaming=True,
    json_mode=True,
    tool_calling=False,
    system_role=True,
    seeded_determinism=True,
    max_context_tokens=128_000,
    max_output_tokens=8_192,
)
"""A production-grade model shape. ``tool_calling`` stays False by default.

That is deliberate rather than an oversight: PRD §3 rules out agentic tool use for v1,
and architecture §8.3 relies on the generation model having no tool surface as its
strongest injection defence. A capability default that made tools available would weaken
that guarantee for anyone who forgot to think about it.
"""
