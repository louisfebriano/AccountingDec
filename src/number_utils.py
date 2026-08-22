"""Normalisasi bilangan lisan bahasa Indonesia untuk input hasil transkripsi."""

import re
from typing import Dict, List, Optional

_UNITS: Dict[str, int] = {
    "nol": 0,
    "satu": 1,
    "dua": 2,
    "tiga": 3,
    "empat": 4,
    "lima": 5,
    "enam": 6,
    "tujuh": 7,
    "delapan": 8,
    "sembilan": 9,
}
_SPECIAL_VALUES = {"sepuluh": 10, "sebelas": 11}
_NUMBER_WORDS = tuple(
    list(_UNITS)
    + list(_SPECIAL_VALUES)
    + ["belas", "puluh", "seratus", "ratus", "seribu", "ribu", "sejuta", "juta"]
)
_WORD_ALTERNATIVES = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
_NUMBER_PHRASE_PATTERN = re.compile(
    rf"\b(?:{_WORD_ALTERNATIVES})(?:[\s-]+(?:{_WORD_ALTERNATIVES}))*\b",
    re.IGNORECASE,
)


def _parse_under_hundred(words: List[str]) -> Optional[int]:
    """Parse frasa bilangan 0-99 yang strukturnya tidak ambigu."""
    if not words:
        return 0
    if len(words) == 1:
        if words[0] in _UNITS:
            return _UNITS[words[0]]
        return _SPECIAL_VALUES.get(words[0])
    if len(words) == 2 and words[0] in _UNITS:
        unit = _UNITS[words[0]]
        if words[1] == "belas" and 1 <= unit <= 9:
            return 10 + unit
        if words[1] == "puluh" and 1 <= unit <= 9:
            return unit * 10
    if (
        len(words) == 3
        and words[0] in _UNITS
        and words[1] == "puluh"
        and words[2] in _UNITS
        and 1 <= _UNITS[words[0]] <= 9
    ):
        return (_UNITS[words[0]] * 10) + _UNITS[words[2]]
    return None


def _parse_under_thousand(words: List[str]) -> Optional[int]:
    """Parse frasa bilangan 0-999."""
    if not words:
        return 0

    hundreds = 0
    remainder = words
    if words[0] == "seratus":
        hundreds = 100
        remainder = words[1:]
    elif len(words) >= 2 and words[0] in _UNITS and words[1] == "ratus":
        multiplier = _UNITS[words[0]]
        if not 1 <= multiplier <= 9:
            return None
        hundreds = multiplier * 100
        remainder = words[2:]

    under_hundred = _parse_under_hundred(remainder)
    if under_hundred is None:
        return None
    return hundreds + under_hundred


def _parse_number_phrase(phrase: str) -> Optional[int]:
    """Ubah satu frasa bilangan Indonesia hingga skala juta menjadi integer."""
    words = phrase.lower().replace("-", " ").split()
    expanded: List[str] = []
    for word in words:
        if word == "seribu":
            expanded.extend(["satu", "ribu"])
        elif word == "sejuta":
            expanded.extend(["satu", "juta"])
        else:
            expanded.append(word)
    words = expanded

    if words.count("juta") > 1 or words.count("ribu") > 1:
        return None

    total = 0
    if "juta" in words:
        index = words.index("juta")
        multiplier = _parse_under_thousand(words[:index])
        if multiplier is None or multiplier == 0:
            return None
        total += multiplier * 1_000_000
        words = words[index + 1:]

    if "ribu" in words:
        index = words.index("ribu")
        multiplier = _parse_under_thousand(words[:index])
        if multiplier is None or multiplier == 0:
            return None
        total += multiplier * 1_000
        words = words[index + 1:]

    remainder = _parse_under_thousand(words)
    if remainder is None:
        return None
    return total + remainder


def normalize_indonesian_numbers(text: str) -> str:
    """Ganti frasa bilangan Indonesia yang didukung dengan digit desimal."""
    if not text:
        return text

    def replace_phrase(match: re.Match) -> str:
        before = text[:match.start()].rstrip().lower()
        after = text[match.end():].lstrip().lower()
        if before.endswith("koma") or after.startswith("koma"):
            return match.group(0)
        value = _parse_number_phrase(match.group(0))
        return str(value) if value is not None else match.group(0)

    return _NUMBER_PHRASE_PATTERN.sub(replace_phrase, text)
