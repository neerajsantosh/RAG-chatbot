from __future__ import annotations

import re
from typing import Any, dict, list, set

from packages.safety.patterns import PII_PATTERNS, SECRET_PATTERNS, REDACTED


def detect_pii(text: str) -> list[str]:
    """Detect PII patterns in text, return list of detected PII types."""
    detected: list[str] = []
    for pattern, pii_type in PII_PATTERNS:
        if pattern.search(text):
            detected.append(pii_type)
    return detected


def detect_secrets(text: str) -> list[str]:
    """Detect secret/credential patterns in text, return list of detected secret types."""
    detected: list[str] = []
    for pattern, secret_type in SECRET_PATTERNS:
        if pattern.search(text):
            detected.append(secret_type)
    return detected


def redact_text(text: str) -> str:
    """Redact PII and secrets from text, returning sanitized version."""
    result = text
    # Replace PII patterns
    for pattern, _ in PII_PATTERNS:
        result = pattern.sub(REDACTED, result)
    # Replace secret patterns
    for pattern, _ in SECRET_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def redact_dict(data: dict[str, Any], *, extra_safe: set[str] | None = None) -> dict[str, Any]:
    """Redact content-bearing values in a dictionary for logging safety."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = redact_text(value)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, extra_safe=extra_safe)
        elif isinstance(value, (list, tuple)):
            result[key] = [
                redact_text(item) if isinstance(item, str) else item for item in value
            ]
        else:
            result[key] = value
    return result