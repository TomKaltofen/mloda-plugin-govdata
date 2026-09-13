"""BBSR Umsteigeschluessel Kreise loader (proportional re-basing keys)."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mloda_plugin_govdata.feature_groups.govdata.core.cache import DownloadCache
from mloda_plugin_govdata.harmonization.keys import repair_bbsr_kreis_key

from .download import fetch_pinned, load_workbook
from .sources import BBSR_KREISE

_SHEET_NAME = re.compile(r"^(\d{4})-(\d{4})$")
_KEY_HEADER = re.compile(r"^kreise31\.12\.(\d{4})")
_NAME_HEADER = re.compile(r"^kreisname(\d{4})$")
_UMLAUTS = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})

# Columns found by header text, not position: sheets before the SvB series began carry no employee columns.
_COLUMNS: dict[str, Callable[[str], bool]] = {
    "area_share": lambda text: text.startswith("flachenproportional"),
    "population_share": lambda text: text.startswith("bevolkerungsproportional"),
    "employee_share": lambda text: text.startswith("beschaftigtenproportional"),
    "area_km2": lambda text: text.startswith("flacheam"),
    "population_thousands": lambda text: text.startswith("bevolkerungam"),
    "svb_thousands": lambda text: "beschaftigteam" in text,
}
_REQUIRED = ("area_share", "population_share", "area_km2", "population_thousands")


@dataclass(frozen=True)
class UmsteigeschluesselRow:
    from_year: int
    to_year: int
    source_key: str
    source_name: str
    area_share: float
    population_share: float
    employee_share: float | None  # None on the early sheets without the employee columns
    area_km2: float
    population_thousands: float
    svb_thousands: float | None  # sozialversicherungspflichtig Beschaeftigte (employees liable for social insurance)
    target_key: str
    target_name: str


def _normalize(cell: Any) -> str:
    return re.sub(r"[\s\-]+", "", str(cell).lower().translate(_UMLAUTS))


def _columns(header: tuple[Any, ...], name: str, from_year: int, to_year: int) -> dict[str, int]:
    """Maps row fields to header positions; direction is data, so the key Stichtage must match the sheet name."""
    found: dict[str, int] = {}
    stichtage: list[int] = []
    names: list[int] = []
    for index, cell in enumerate(header):
        text = _normalize(cell)
        key_match = _KEY_HEADER.match(text)
        if key_match is not None:
            stichtage.append(int(key_match.group(1)))
            found["target_key" if stichtage[1:] else "source_key"] = index
        elif text.startswith("kreisname"):
            names.append(index)
        else:
            found.update({field: index for field, matches in _COLUMNS.items() if matches(text)})
    if tuple(stichtage) != (from_year, to_year):
        raise ValueError(f"sheet {name}: header Stichtage {tuple(stichtage)} do not match the sheet name's year pair")
    if len(names) != 2:
        raise ValueError(f"sheet {name}: expected two Kreisname columns, got {len(names)}: {header!r}")
    missing = [field for field in _REQUIRED if field not in found]
    if missing:
        raise ValueError(f"sheet {name}: header lacks {missing}: {header!r}")
    # Each Kreisname column must sit right after its own key column (verified against every sheet
    # of the real pinned file); this alone still accepts a header where two distinct-year labels
    # are swapped between the two (still adjacent) slots, so cross-check the labels' own years too,
    # skipping the check when they are equal: a real sheet (1996-1997) repeats one year on both.
    if names != [found["source_key"] + 1, found["target_key"] + 1]:
        raise ValueError(
            f"sheet {name}: Kreisname columns {names} do not sit next to their key columns "
            f"[{found['source_key']}, {found['target_key']}]: {header!r}"
        )
    label_years = [m.group(1) for cell in (header[i] for i in names) if (m := _NAME_HEADER.match(_normalize(cell)))]
    labels_distinguish = len(label_years) == 2 and label_years[0] != label_years[1]
    if labels_distinguish and (int(label_years[0]), int(label_years[1])) != (from_year, to_year):
        raise ValueError(
            f"sheet {name}: Kreisname labels {label_years} contradict the sheet's year pair "
            f"{(from_year, to_year)}: {header!r}"
        )
    found["source_name"], found["target_name"] = names
    return found


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _parse_sheet(sheet: Any, name: str, from_year: int, to_year: int) -> list[UmsteigeschluesselRow]:
    rows: list[UmsteigeschluesselRow] = []
    row_iter = sheet.iter_rows(values_only=True)
    header = next(row_iter, None)
    if header is None:
        raise ValueError(f"sheet {name}: no header row")
    at = _columns(header, name, from_year, to_year)
    for cells in row_iter:
        if cells[at["source_key"]] is None:  # trailing all-empty row ends the sheet's data
            break
        rows.append(
            UmsteigeschluesselRow(
                from_year=from_year,
                to_year=to_year,
                source_key=repair_bbsr_kreis_key(cells[at["source_key"]]),
                source_name=str(cells[at["source_name"]]),
                area_share=float(cells[at["area_share"]]),
                population_share=float(cells[at["population_share"]]),
                employee_share=_optional_float(cells[at["employee_share"]]) if "employee_share" in at else None,
                area_km2=float(cells[at["area_km2"]]),
                population_thousands=float(cells[at["population_thousands"]]),
                svb_thousands=_optional_float(cells[at["svb_thousands"]]) if "svb_thousands" in at else None,
                target_key=repair_bbsr_kreis_key(cells[at["target_key"]]),
                target_name=str(cells[at["target_name"]]),
            )
        )
    return rows


def parse_bbsr_kreise_workbook(path: str | os.PathLike[str]) -> list[UmsteigeschluesselRow]:
    """Parses every year-pair sheet of a BBSR Kreise Umsteigeschluessel workbook.

    The full file spans 1990 to 2024, one sheet per consecutive year pair named
    ``<y>-<y+1>``; direction is old to new (forward), read from the sheet name and
    cross-checked against the header's Stichtag cells. Does not validate per-key share
    sums: at least one sheet carries a known upstream defect where split shares land on
    identity rows instead of a transfer row (see the fixture ``NOTICE``); asserting and
    raising on that is ``harmonization/rebase.py``'s job, not this one's.
    """
    workbook = load_workbook(path)
    rows: list[UmsteigeschluesselRow] = []
    for sheet_name in workbook.sheetnames:
        match = _SHEET_NAME.match(sheet_name)
        if match is None:
            continue  # not a year-pair sheet; skip defensively rather than raise
        from_year, to_year = int(match.group(1)), int(match.group(2))
        rows.extend(_parse_sheet(workbook[sheet_name], sheet_name, from_year, to_year))
    return rows


def load_bbsr_kreise(cache: DownloadCache, *, revalidate: bool = False) -> list[UmsteigeschluesselRow]:
    """Fetches (offline-cache-first) and parses the BBSR Kreise Umsteigeschluessel."""
    path = fetch_pinned(cache, BBSR_KREISE, revalidate=revalidate)
    return parse_bbsr_kreise_workbook(path)
