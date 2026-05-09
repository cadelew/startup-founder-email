"""Text cleanup helpers shared by parsing and validation code."""

from __future__ import annotations

import re


def strip_zero_width_characters(text: str) -> str:
    """Remove invisible characters that commonly appear in copied page text."""

    zero_width_characters = ("\u200b", "\u200c", "\u200d", "\ufeff")
    cleaned_text = text
    for zero_width_character in zero_width_characters:
        cleaned_text = cleaned_text.replace(zero_width_character, "")
    return cleaned_text


def collapse_whitespace(text: str) -> str:
    """Collapse repeated whitespace to a single space."""

    return re.sub(r"\s+", " ", text).strip()


def normalize_visible_text(text: str) -> str:
    """Apply the standard cleanup used before parsing page text."""

    return collapse_whitespace(strip_zero_width_characters(text))
