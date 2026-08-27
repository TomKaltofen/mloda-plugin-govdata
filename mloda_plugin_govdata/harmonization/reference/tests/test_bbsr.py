from pathlib import Path

from mloda_plugin_govdata.harmonization.reference.bbsr import parse_bbsr_kreise_workbook


def test_parses_all_three_fixture_sheets(fixtures_dir: Path) -> None:
    rows = parse_bbsr_kreise_workbook(fixtures_dir / "bbsr-ref-kreise-extract.xlsx")
    year_pairs = {(r.from_year, r.to_year) for r in rows}
    assert year_pairs == {(2013, 2014), (2015, 2016), (2020, 2021)}
    assert len(rows) == 21  # 8 + 7 + 6 rows across the three sheets


def test_repairs_excel_mangled_kreis_keys(fixtures_dir: Path) -> None:
    rows = parse_bbsr_kreise_workbook(fixtures_dir / "bbsr-ref-kreise-extract.xlsx")
    # Source cells store Kreise as Excel-mangled ints (e.g. 3152000); every parsed key
    # must already be the repaired 5-digit form, leading zero included.
    for row in rows:
        assert len(row.source_key) == 5
        assert len(row.target_key) == 5


def test_a_split_source_has_several_rows(fixtures_dir: Path) -> None:
    rows = parse_bbsr_kreise_workbook(fixtures_dir / "bbsr-ref-kreise-extract.xlsx")
    cochem_2013_2014 = [r for r in rows if r.from_year == 2013 and r.source_key == "07135"]
    assert len(cochem_2013_2014) == 2  # Cochem-Zell split across an identity row and a transfer row
    assert {r.target_key for r in cochem_2013_2014} == {"07135", "07140"}


def test_goettingen_merger_direction_is_old_to_new(fixtures_dir: Path) -> None:
    rows = parse_bbsr_kreise_workbook(fixtures_dir / "bbsr-ref-kreise-extract.xlsx")
    merger_rows = [r for r in rows if r.from_year == 2015 and r.source_key in {"03152", "03156"}]
    assert len(merger_rows) == 2
    assert all(r.target_key == "03159" for r in merger_rows)  # forward: old Kreise into the merged one


def test_known_upstream_defect_is_reproduced_not_fixed(fixtures_dir: Path) -> None:
    # ADR 0006 / fixture NOTICE: sheet 2015-2016 carries the 2013-2014 split shares on
    # identity rows for 07135 and 07137; this loader loads them faithfully (no share-sum
    # assertion here, that is the slice-9 re-basing loader's job).
    rows = parse_bbsr_kreise_workbook(fixtures_dir / "bbsr-ref-kreise-extract.xlsx")
    cochem_2015_2016 = next(r for r in rows if r.from_year == 2015 and r.source_key == "07135")
    assert cochem_2015_2016.target_key == "07135"  # identity row
    assert cochem_2015_2016.area_share != 1.0  # yet carries a non-identity share, the defect
