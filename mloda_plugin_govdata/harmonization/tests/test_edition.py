from pathlib import Path

import pytest

from mloda_plugin_govdata.harmonization.edition import load_edition
from mloda_plugin_govdata.harmonization.reference.eurostat import parse_lau_nuts_de_workbook
from mloda_plugin_govdata.harmonization.reference.gv_isys import parse_gv_isys_workbook


class _FakeCache:
    """Stands in for DownloadCache: load_edition only calls fetch_pinned, which this bypasses."""


def test_load_edition_from_real_fixture(monkeypatch: pytest.MonkeyPatch, reference_fixtures_dir: Path) -> None:
    rows = parse_lau_nuts_de_workbook(reference_fixtures_dir / "eurostat-lau-nuts-de-extract.xlsx")
    monkeypatch.setattr("mloda_plugin_govdata.harmonization.edition.load_lau_nuts_de", lambda cache, **kwargs: rows)
    edition = load_edition(_FakeCache())  # type: ignore[arg-type]
    assert edition.nuts_version == "2024"
    assert edition.gebietsstand == "2024"
    assert edition.year_range == (2024, 2024)
    assert len(edition.lau_rows) == 5


def test_load_edition_year_range_widens_with_gv_isys_history(
    monkeypatch: pytest.MonkeyPatch, reference_fixtures_dir: Path
) -> None:
    rows = parse_lau_nuts_de_workbook(reference_fixtures_dir / "eurostat-lau-nuts-de-extract.xlsx")
    changes = parse_gv_isys_workbook(reference_fixtures_dir / "gv-isys-2016-extract.xlsx")
    monkeypatch.setattr("mloda_plugin_govdata.harmonization.edition.load_lau_nuts_de", lambda cache, **kwargs: rows)
    edition = load_edition(_FakeCache(), gv_isys_changes=changes)  # type: ignore[arg-type]
    assert edition.year_range == (2016, 2024)
    assert edition.gv_isys_changes == tuple(changes)


def test_load_edition_raises_on_multiple_periods(monkeypatch: pytest.MonkeyPatch, reference_fixtures_dir: Path) -> None:
    rows = parse_lau_nuts_de_workbook(reference_fixtures_dir / "eurostat-lau-nuts-de-extract.xlsx")
    mixed = [rows[0], rows[1].__class__(**{**rows[1].__dict__, "period": 2021})]
    monkeypatch.setattr("mloda_plugin_govdata.harmonization.edition.load_lau_nuts_de", lambda cache, **kwargs: mixed)
    with pytest.raises(ValueError, match="multiple PERIOD values"):
        load_edition(_FakeCache())  # type: ignore[arg-type]
