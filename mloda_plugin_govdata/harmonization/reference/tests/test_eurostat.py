from pathlib import Path

from mloda_plugin_govdata.harmonization.reference import eurostat
from mloda_plugin_govdata.harmonization.reference.eurostat import (
    parse_lau_nuts_de_workbook,
    parse_nuts_correspondence_workbook,
)


def test_parses_lau_nuts_de_rows(fixtures_dir: Path) -> None:
    rows = parse_lau_nuts_de_workbook(fixtures_dir / "eurostat-lau-nuts-de-extract.xlsx")
    assert len(rows) == 5
    by_lau = {r.lau_code: r for r in rows}
    assert by_lau["11000000"].nuts3 == "DE300"  # Berlin
    assert by_lau["03159501"].nuts3 == "DE91C"  # Harz gemeindefreies Gebiet
    assert all(r.period == 2024 for r in rows)


def test_lau_code_preserves_leading_zeros(fixtures_dir: Path) -> None:
    rows = parse_lau_nuts_de_workbook(fixtures_dir / "eurostat-lau-nuts-de-extract.xlsx")
    assert all(len(r.lau_code) == 8 for r in rows)
    assert all(r.lau_code.isdigit() for r in rows)


def test_parses_nuts_correspondence_overview(fixtures_dir: Path) -> None:
    overview = parse_nuts_correspondence_workbook(fixtures_dir / "eurostat-nuts-correspondence-extract.xlsx")
    assert overview.kreise == 401
    assert overview.gemeinden == 10957
    assert overview.edition_label == "NUTS 2027 and LAU 2025"


def test_overview_edition_differs_from_mapping_edition(fixtures_dir: Path) -> None:
    # ADR 0006, Edition identity: the overview table's own label is a different, not-yet-
    # current edition from the NUTS 2024 crosswalk the mapper actually uses.
    overview = parse_nuts_correspondence_workbook(fixtures_dir / "eurostat-nuts-correspondence-extract.xlsx")
    assert "2024" not in overview.edition_label


def test_lau_loader_docstring_documents_the_partial_validation_caveat() -> None:
    docstring = eurostat.parse_lau_nuts_de_workbook.__doc__ or ""
    assert "Cyprus" in docstring
    assert "validated" in docstring
