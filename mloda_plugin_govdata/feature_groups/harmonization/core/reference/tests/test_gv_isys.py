from datetime import date
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from mloda_plugin_govdata.feature_groups.govdata.core.cache import DownloadCache
from mloda_plugin_govdata.feature_groups.harmonization.core.reference import gv_isys
from mloda_plugin_govdata.feature_groups.harmonization.core.reference.gv_isys import (
    load_gv_isys_changes,
    parse_gv_isys_workbook,
)
from mloda_plugin_govdata.feature_groups.harmonization.core.reference.sources import GV_ISYS_2016_SHA256, gv_isys_source


def test_parses_kreis_merger_and_gemeinde_row(fixtures_dir: Path) -> None:
    changes = parse_gv_isys_workbook(fixtures_dir / "gv-isys-2016-extract.xlsx")
    assert len(changes) == 3
    kreis_changes = [c for c in changes if c.level == "Kreis"]
    gemeinde_changes = [c for c in changes if c.level == "Gemeinde"]
    assert {c.from_ags for c in kreis_changes} == {"03152", "03156"}
    assert all(c.to_ags == "03159" for c in kreis_changes)
    assert len(gemeinde_changes) == 1
    assert gemeinde_changes[0].from_ags == "03156501"
    assert gemeinde_changes[0].to_ags == "03159501"


def test_ags_values_are_stripped_of_trailing_padding(fixtures_dir: Path) -> None:
    # The raw sheet stores the AGS column with trailing whitespace ("03152   ").
    changes = parse_gv_isys_workbook(fixtures_dir / "gv-isys-2016-extract.xlsx")
    assert all(c.from_ags == c.from_ags.strip() for c in changes)


def _behind_a_cover_sheet(extract: Path, tmp_path: Path, *, data: bool = True, trailing: str | None = None) -> Path:
    """The extract laid out like the published file: a cover sheet first, rows padded past the 13 columns."""
    source = openpyxl.load_workbook(extract).active
    workbook = openpyxl.Workbook()
    cover = workbook.active
    assert source is not None and cover is not None
    cover.title = "Deckblatt"
    sheet = workbook.create_sheet("Gebietsaenderungen 2016")
    sheet.cell(row=1, column=20, value="widens the dimension")
    for row in source.iter_rows(values_only=True) if data else ():
        sheet.append(row if trailing is None or not row[0] else (*row, trailing))
    made = tmp_path / "made.xlsx"
    workbook.save(made)
    return made


def test_reads_the_data_sheet_behind_a_cover_sheet_with_padded_rows(fixtures_dir: Path, tmp_path: Path) -> None:
    extract = fixtures_dir / "gv-isys-2016-extract.xlsx"
    assert parse_gv_isys_workbook(_behind_a_cover_sheet(extract, tmp_path)) == parse_gv_isys_workbook(extract)


@pytest.mark.parametrize(
    ("layout", "message"),
    [({"data": False}, "No GV-ISys change rows"), ({"trailing": "extra"}, "cells past column 13")],
)
def test_an_unexpected_layout_fails_loudly(
    layout: dict[str, Any], message: str, fixtures_dir: Path, tmp_path: Path
) -> None:
    made = _behind_a_cover_sheet(fixtures_dir / "gv-isys-2016-extract.xlsx", tmp_path, **layout)
    with pytest.raises(ValueError, match=message):
        parse_gv_isys_workbook(made)


def test_effective_dates_parsed(fixtures_dir: Path) -> None:
    changes = parse_gv_isys_workbook(fixtures_dir / "gv-isys-2016-extract.xlsx")
    assert all(c.effective_date_legal == date(2016, 11, 1) for c in changes)
    assert all(c.effective_date_statistical == date(2016, 11, 1) for c in changes)


def test_shared_change_id_groups_a_merger(fixtures_dir: Path) -> None:
    changes = parse_gv_isys_workbook(fixtures_dir / "gv-isys-2016-extract.xlsx")
    assert len({c.change_id for c in changes}) == 1  # one merger event, several affected units


def test_load_applies_the_known_2016_hash_without_an_explicit_sha256(monkeypatch: pytest.MonkeyPatch) -> None:
    # A caller who forgets to pass sha256 for 2016 must still get the pin: the known hash
    # applies automatically rather than silently accepting drifted reference data.
    captured: dict[str, Any] = {}

    def fake_fetch_pinned(cache: Any, source: Any, *, revalidate: bool = False) -> str:
        captured["source"] = source
        return "unused"

    monkeypatch.setattr(gv_isys, "fetch_pinned", fake_fetch_pinned)
    monkeypatch.setattr(gv_isys, "parse_gv_isys_workbook", lambda path: [])

    load_gv_isys_changes(2016, cache=object())  # type: ignore[arg-type]
    assert captured["source"].sha256 == GV_ISYS_2016_SHA256 == gv_isys_source(2016).sha256


def test_load_leaves_an_unknown_year_unpinned(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_fetch_pinned(cache: Any, source: Any, *, revalidate: bool = False) -> str:
        captured["source"] = source
        return "unused"

    monkeypatch.setattr(gv_isys, "fetch_pinned", fake_fetch_pinned)
    monkeypatch.setattr(gv_isys, "parse_gv_isys_workbook", lambda path: [])

    load_gv_isys_changes(2017, cache=object())  # type: ignore[arg-type]
    assert captured["source"].sha256 is None
    assert gv_isys_source(2017).sha256 is None


@pytest.mark.live
def test_the_pinned_real_2016_file_holds_the_goettingen_merger(tmp_path: Path) -> None:
    with DownloadCache(tmp_path) as cache:
        changes = load_gv_isys_changes(2016, cache, revalidate=True)
    merged = {(c.from_ags, c.to_ags) for c in changes if c.level == "Kreis"}
    assert merged == {("03152", "03159"), ("03156", "03159")}
