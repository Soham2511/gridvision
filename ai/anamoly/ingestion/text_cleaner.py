"""Normalize extracted text without changing its factual content."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    """Remove extraction artifacts and normalize whitespace."""
    text = text.replace("\x00", " ").replace("\ufeff", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return text.strip()

