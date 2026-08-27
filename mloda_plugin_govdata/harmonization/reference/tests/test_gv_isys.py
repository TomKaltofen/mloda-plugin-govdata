from datetime import date
from pathlib import Path

from mloda_plugin_govdata.harmonization.reference.gv_isys import parse_gv_isys_workbook


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


def test_effective_dates_parsed(fixtures_dir: Path) -> None:
    changes = parse_gv_isys_workbook(fixtures_dir / "gv-isys-2016-extract.xlsx")
    assert all(c.effective_date_legal == date(2016, 11, 1) for c in changes)
    assert all(c.effective_date_statistical == date(2016, 11, 1) for c in changes)


def test_shared_change_id_groups_a_merger(fixtures_dir: Path) -> None:
    changes = parse_gv_isys_workbook(fixtures_dir / "gv-isys-2016-extract.xlsx")
    assert len({c.change_id for c in changes}) == 1  # one merger event, several affected units
