from __future__ import annotations

import re
import unicodedata


_TURKISH_ASCII_MAP = str.maketrans(
    {
        "ı": "i",
        "ş": "s",
        "ğ": "g",
        "ç": "c",
        "ö": "o",
        "ü": "u",
    }
)


def to_canonical_location(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    lowered = text.casefold().translate(_TURKISH_ASCII_MAP)
    ascii_text = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", ascii_text)
    normalized_spaces = re.sub(r"\s+", " ", cleaned).strip()
    return normalized_spaces or None
