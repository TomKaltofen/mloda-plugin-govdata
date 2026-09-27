"""AGS/ARS key detection and normalization.

Keys are strings with leading zeros preserved end to end. AGS (Amtlicher
Gemeindeschluessel) comes in three levels by digit count: Land (2), Kreis (5),
Gemeinde (8). ARS (Regionalschluessel) is a distinct 12-digit key. Excel-mangled
integer keys (a leading zero stripped by the spreadsheet) are only ever repaired
through an explicit, source-specific function such as :func:`repair_bbsr_kreis_key`,
never guessed generically.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum


class AgsLevel(IntEnum):
    LAND = 2
    KREIS = 5
    GEMEINDE = 8


ARS_LENGTH = 12
_VALID_LENGTHS = frozenset({AgsLevel.LAND, AgsLevel.KREIS, AgsLevel.GEMEINDE, ARS_LENGTH})


def detect_level(key: str) -> int:
    """Digit-count level of an AGS/ARS key already in string form: 2, 5, 8, or 12.

    Raises ``ValueError`` if ``key`` is not purely numeric or has any other length.
    """
    if not key.isdigit():
        raise ValueError(f"{key!r} is not a numeric AGS/ARS key")
    if len(key) not in _VALID_LENGTHS:
        raise ValueError(f"{key!r} has {len(key)} digits, not a valid AGS (2/5/8) or ARS (12) length")
    return len(key)


def normalize_key(value: int | str, *, level: int) -> str:
    """Zero-pads ``value`` to ``level`` digits. Raises if it does not fit or is not numeric."""
    if level not in _VALID_LENGTHS:
        raise ValueError(f"{level} is not a valid AGS/ARS key length")
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError(f"{value!r} is not a numeric AGS/ARS key")
    if len(text) > level:
        raise ValueError(f"{value!r} has more than {level} digits, cannot pad to a level-{level} key")
    return text.zfill(level)


def repair_bbsr_kreis_key(value: int | str) -> str:
    """Repairs a BBSR Kreis key mangled by Excel's integer coercion.

    The BBSR Kreise Umsteigeschluessel stores a 5-digit Kreis key as an 8-digit
    number with a fixed ``000`` Gemeinde suffix (e.g. ``3152000`` for Kreis
    ``03152``), because Excel strips the AGS's leading zero. Repairs to the
    5-digit Kreis key only when that suffix holds; raises otherwise so a
    genuine (non-Kreis) row is never silently truncated.
    """
    text = normalize_key(value, level=AgsLevel.GEMEINDE)
    if not text.endswith("000"):
        raise ValueError(f"BBSR key {value!r} has no '000' Gemeinde suffix; not repairable to a Kreis key")
    return text[:5]


def normalize_keys(values: Iterable[str]) -> tuple[list[str], int]:
    """Validates a batch of same-level AGS/ARS string keys, returning them with their level.

    Every key must already carry its leading zeros; this does not pad. Raises if the
    batch is empty, mixes levels (2/5/8/12 digits), or contains a malformed key.
    """
    keys = list(values)
    if not keys:
        raise ValueError("no keys given")
    levels = {detect_level(key) for key in keys}
    if len(levels) > 1:
        raise ValueError(f"mixed AGS/ARS levels in one input: {sorted(levels)}")
    return keys, levels.pop()
