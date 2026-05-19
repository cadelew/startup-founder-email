from startup_founder_email.text_normalization import (
    collapse_whitespace,
    normalize_email_token,
    normalize_visible_text,
    strip_zero_width_characters,
    transliterate_to_ascii,
)


def test_strip_zero_width_characters_removes_invisible_text() -> None:
    assert strip_zero_width_characters("Ada\u200b Lovelace") == "Ada Lovelace"


def test_collapse_whitespace_reduces_repeated_spacing() -> None:
    assert collapse_whitespace("Ada\n\n   Lovelace") == "Ada Lovelace"


def test_normalize_visible_text_applies_standard_cleanup() -> None:
    assert normalize_visible_text(" Ada\u200b\n  Lovelace ") == "Ada Lovelace"


def test_transliterate_to_ascii_maps_accents_and_special_letters() -> None:
    assert transliterate_to_ascii("Chávez") == "Chavez"
    assert transliterate_to_ascii("José") == "Jose"
    assert transliterate_to_ascii("Müller") == "Muller"
    assert transliterate_to_ascii("François") == "Francois"
    assert transliterate_to_ascii("Björk") == "Bjork"
    assert transliterate_to_ascii("Straße") == "Strasse"
    assert transliterate_to_ascii("Łukasz") == "Lukasz"
    assert transliterate_to_ascii("Æthelred") == "Aethelred"
    assert transliterate_to_ascii("Søren") == "Soren"


def test_normalize_email_token_transliterates_for_email_local_parts() -> None:
    assert normalize_email_token("Chávez-Torres") == "chaveztorres"
    assert normalize_email_token("Federico") == "federico"
    assert normalize_email_token("O'Brien") == "obrien"
    assert normalize_email_token(None) == ""
    assert normalize_email_token("") == ""
