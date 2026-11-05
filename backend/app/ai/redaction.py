"""Small deterministic redaction helpers for future provider-facing text."""

from __future__ import annotations

import re


_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Z0-9._~+/-]+=*")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\s*([=:])\s*[^\s,;]+"
)


def redact_sensitive_text(value: str) -> str:
    """Mask common direct identifiers and credentials before diagnostic logging."""
    value = _EMAIL.sub("[REDACTED_EMAIL]", value)
    value = _PHONE.sub("[REDACTED_PHONE]", value)
    value = _BEARER.sub(r"\1[REDACTED]", value)
    return _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", value)
