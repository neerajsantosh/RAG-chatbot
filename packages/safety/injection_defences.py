from __future__ import annotations

import re
from typing import Final

# Versioned detection patterns - a false positive can be traced to a version
INJECTION_PATTERN_VERSION: Final = "1.0"

# Prompt-side defence primitives
_DELIMITER_PATTERN: Final = re.compile(r"""\{\{""")
"""Detects code block delimiters that could be used for indirect prompt injection."""

_INSTRUCTION_ISOLATION_PATTERN: Final = re.compile(
    r"\b(?:ignore|override|disregard|forget|not|stop)\s+.*?(?:instructions|rules|policies)\b",
    re.IGNORECASE,
)
"""Detects direct instruction override attempts in prompts."""

_ROLE_PLAY_PATTERN: Final = re.compile(
    r"\b(you are|pretend|role-play|act as|simulate)\s+.*?(?:admin|operator|authority|figure of authority)\b",
    re.IGNORECASE,
)
"""Detects role-play attempts to override system behaviour."""


def isolate_instructions(prompt: str) -> tuple[str, list[str]]:
    """Isolate and annotate instruction-like segments in a prompt.

    Returns (cleaned_prompt, annotated_segments) where annotated_segments
    contain the isolated instruction patterns for audit purposes.
    """
    annotated: list[str] = []
    # Find and marker instruction patterns
    matches = _INSTRUCTION_ISOLATION_PATTERN.finditer(prompt)
    for match in matches:
        annotated.append(f"[INSTRUCTION:{match.group()}]")
        # Replace with placeholder to isolate the instruction
        prompt = prompt[: match.start()] + "[INSTRUCTION-REDACTED]" + prompt[match.end():]

    role_matches = _ROLE_PLAY_PATTERN.finditer(prompt)
    for match in role_matches:
        annotated.append(f"[ROLE-PLAY:{match.group()}]")
        prompt = prompt[: match.start()] + "[ROLE-PLAY-REDACTED]" + prompt[match.end():]

    delimiter_matches = _DELIMITER_PATTERN.finditer(prompt)
    for match in delimiter_matches:
        annotated.append(f"[DELIMITER:{match.group()}]")

    return prompt, annotated


def neutralise_prompt(prompt: str) -> str:
    """Apply defence primitives to neutralise prompt injection attempts.

    Returns a sanitized prompt safe for model consumption.
    """
    # Isolate instructions first
    cleaned, _ = isolate_instructions(prompt)
    # Then handle delimiters
    cleaned = _DELIMITER_PATTERN.sub("[CODE-BLOCK]", cleaned)
    return cleaned