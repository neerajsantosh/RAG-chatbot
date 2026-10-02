from __future__ import annotations

import re
from typing import Final

# Patterns for PII detection
PII_PATTERNS: Final = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN (Social Security Number)"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "Credit Card Number"),
    (re.compile(r"\b[A-Z]{2,3}\d{6,8}\b"), "Product/Serial Number"),
]

# Patterns for secret/credential detection
SECRET_PATTERNS: Final = [
    (re.compile(r"\bsk_live_[A-Za-z0-9]{24}\b"), "Stripe Live Key"),
    (re.compile(r"\bsk_test_[A-Za-z0-9]{24}\b"), "Stripe Test Key"),
    (re.compile(r"\b[A-Z0-9]{32}\b"), "Generic API Key (32 hex chars)"),
    # Inline key assignment
    (re.compile("(?:api|secret|key)_key" r"\s*=\s*[^\\s]+"), "Inline key assignment"),
]