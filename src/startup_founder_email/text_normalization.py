"""Text cleanup helpers shared by parsing and validation code."""

from __future__ import annotations

import re
import unicodedata


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


# Latin letters that NFKD does not decompose into ASCII-friendly parts.
_LATIN_SPECIAL_CASES: dict[str, str] = {
    "\u00df": "ss",  # ß
    "\u1e9e": "ss",  # ẞ
    "\u00f8": "o",  # ø
    "\u00d8": "o",  # Ø
    "\u0142": "l",  # ł
    "\u0141": "l",  # Ł
    "\u0111": "d",  # đ
    "\u0110": "d",  # Đ
    "\u00fe": "th",  # þ
    "\u00de": "th",  # Þ
    "\u00f0": "d",  # ð
    "\u00d0": "d",  # Ð
    "\u00e6": "ae",  # æ
    "\u00c6": "ae",  # Æ
    "\u0153": "oe",  # œ
    "\u0152": "oe",  # Œ
    "\u0131": "i",  # ı (dotless i)
    "\u0130": "i",  # İ
    "\u0144": "n",  # ń — NFKD usually handles; kept for safety
    "\u0143": "n",  # Ń
}


def apply_latin_special_case_replacements(text: str) -> str:
    """Replace Latin letters that NFKD does not fold to ASCII."""

    result_characters: list[str] = []
    for character in text:
        replacement = _LATIN_SPECIAL_CASES.get(character)
        if replacement is None:
            result_characters.append(character)
            continue
        if character.isupper():
            if len(replacement) == 1:
                result_characters.append(replacement.upper())
            else:
                result_characters.append(replacement[0].upper() + replacement[1:])
        else:
            result_characters.append(replacement)
    return "".join(result_characters)


def transliterate_to_ascii(text: str) -> str:
    """Map Unicode name text to ASCII letters for email local-part guessing."""

    cleaned_text = apply_latin_special_case_replacements(strip_zero_width_characters(text))
    decomposed_text = unicodedata.normalize("NFKD", cleaned_text)
    without_combining_marks = "".join(
        character
        for character in decomposed_text
        if not unicodedata.combining(character)
    )
    return without_combining_marks.encode("ascii", "ignore").decode("ascii")


def normalize_email_token(value: str | None) -> str:
    """Normalize a name token for use in an email local part."""

    if not value:
        return ""
    ascii_text = transliterate_to_ascii(value).lower()
    return re.sub(r"[^a-z0-9]", "", ascii_text)
