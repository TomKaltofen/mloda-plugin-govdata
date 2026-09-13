"""The 16 Laender by AGS-2 code: a name check for Land rows (D2), never the join key."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

LAND_NAMES: Mapping[str, str] = MappingProxyType(
    {
        "01": "Schleswig-Holstein",
        "02": "Hamburg",
        "03": "Niedersachsen",
        "04": "Bremen",
        "05": "Nordrhein-Westfalen",
        "06": "Hessen",
        "07": "Rheinland-Pfalz",
        "08": "Baden-Württemberg",
        "09": "Bayern",
        "10": "Saarland",
        "11": "Berlin",
        "12": "Brandenburg",
        "13": "Mecklenburg-Vorpommern",
        "14": "Sachsen",
        "15": "Sachsen-Anhalt",
        "16": "Thüringen",
    }
)
_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"})  # casefold() already turns ß into ss


class LandNameError(ValueError):
    """A Land row's code and name disagree with the constant, or the set of Laender is not the 16."""


def normalize_land_name(name: str) -> str:
    """Case, surrounding whitespace, and umlaut spelling (``Thüringen`` equals ``Thueringen``) do not count."""
    return " ".join(name.casefold().translate(_FOLD).split())


_CODES_BY_NAME: Mapping[str, str] = MappingProxyType(
    {normalize_land_name(name): code for code, name in LAND_NAMES.items()}
)


def land_name(code: str) -> str:
    try:
        return LAND_NAMES[code]
    except KeyError:
        raise LandNameError(f"{code!r} is not a Land AGS-2 code (01 to 16)") from None


def land_code(name: str) -> str:
    try:
        return _CODES_BY_NAME[normalize_land_name(name)]
    except KeyError:
        raise LandNameError(f"{name!r} is not a Land name") from None


def check_land_names(rows: Iterable[tuple[str, object]], *, complete: bool = True) -> None:
    """Every ``(code, name)`` pair must agree with the constant, no code twice; ``complete`` also wants all 16."""
    problems: list[str] = []
    seen: dict[str, int] = {}
    for position, (code, name) in enumerate(rows):
        expected = LAND_NAMES.get(code)
        if expected is None:
            problems.append(f"row {position}: {code!r} is not a Land code")
            continue
        seen[code] = seen.get(code, 0) + 1
        if not isinstance(name, str):
            problems.append(f"row {position}: {code} has no name ({type(name).__name__})")
        elif normalize_land_name(name) != normalize_land_name(expected):
            problems.append(f"row {position}: {code} is {expected!r}, not {name!r}")
    problems.extend(f"{code} appears {count} times" for code, count in sorted(seen.items()) if count > 1)
    if complete:
        missing = sorted(set(LAND_NAMES) - set(seen))
        if missing:
            problems.append(f"missing Land codes {missing}")
    if problems:
        raise LandNameError("Land rows disagree with the AGS-2 constant: " + "; ".join(problems))
