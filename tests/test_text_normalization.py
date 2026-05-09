from startup_founder_email.text_normalization import (
    collapse_whitespace,
    normalize_visible_text,
    strip_zero_width_characters,
)


def test_strip_zero_width_characters_removes_invisible_text() -> None:
    assert strip_zero_width_characters("Ada\u200b Lovelace") == "Ada Lovelace"


def test_collapse_whitespace_reduces_repeated_spacing() -> None:
    assert collapse_whitespace("Ada\n\n   Lovelace") == "Ada Lovelace"


def test_normalize_visible_text_applies_standard_cleanup() -> None:
    assert normalize_visible_text(" Ada\u200b\n  Lovelace ") == "Ada Lovelace"
