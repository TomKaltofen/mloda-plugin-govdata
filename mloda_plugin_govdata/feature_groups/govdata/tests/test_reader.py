"""Level 2 (recorded) and Level 3 (live) tests for the GovData reader."""

import json
from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from mloda.user import Feature, Options, mloda

from mloda_plugin_govdata.feature_groups.govdata.discovery import ResolvedDistribution
from mloda_plugin_govdata.feature_groups.govdata.locator import GovDataLocator
from mloda_plugin_govdata.feature_groups.govdata.reader import (
    OPTION_WAHL_HEADER_ROWS,
    OPTION_WAHL_LABEL_COLUMNS,
    OPTION_WAHL_SKIPROWS,
    OPTION_WAHL_VALUE_TYPE,
    BundeswahlleiterinReader,
    GovDataFeature,
    GovDataReader,
)

SLUG = "einwohner-nach-altersgruppen-und-stadtbezirken"
PACKAGE_SHOW = "https://ckan.govdata.de/api/3/action/package_show"
KERG_URL = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv"
KERG_MEASURE = "Wahlberechtigte Erststimmen Endgültig"
BERLIN_URL = "https://www.wahlen-berlin.de/wahlen/BE2023/AFSPRAES/agh/Datenexport_AGH2023_Zweitstimme_W_BE.csv"
# The wahlen-berlin.de Datenexport geometry: no preamble, one header row, 12 label
# columns (Adresse..Zeit), then vote counts and German-decimal percentage columns.
BERLIN_OPTIONS: dict[str, object] = {
    BundeswahlleiterinReader.__name__: BERLIN_URL,
    OPTION_WAHL_SKIPROWS: 0,
    OPTION_WAHL_HEADER_ROWS: 1,
    OPTION_WAHL_LABEL_COLUMNS: 12,
    OPTION_WAHL_VALUE_TYPE: "float",
}


def test_feature_group_uses_govdata_reader() -> None:
    assert isinstance(GovDataFeature.input_data(), GovDataReader)


@respx.mock
def test_load_data_level2(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GovDataReader, "cache_dir", str(tmp_path))
    package_show = (fixtures_dir / "package_show.json").read_text(encoding="utf-8")
    csv_bytes = (fixtures_dir / "population_sample.csv").read_bytes()
    distribution_url = json.loads(package_show)["result"]["resources"][0]["url"]

    respx.get(PACKAGE_SHOW).mock(return_value=httpx.Response(200, text=package_show))
    respx.get(distribution_url).mock(return_value=httpx.Response(200, content=csv_bytes, headers={"ETag": '"v1"'}))

    result = mloda.run_all(
        [
            Feature("Einwohner", options={GovDataReader.__name__: SLUG}),
            Feature("Stadtbezirk", options={GovDataReader.__name__: SLUG}),
        ],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert set(table.schema.names) == {"Einwohner", "Stadtbezirk"}
    assert table.num_rows == 1000
    assert table.schema.field("Einwohner").type == pa.int64()


@respx.mock
def test_resolves_without_explicit_compute_framework(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: GovDataFeature must not collide with the built-in ReadFileFeature,
    # so a run_all call with no compute_frameworks pin still resolves to one group.
    monkeypatch.setattr(GovDataReader, "cache_dir", str(tmp_path))
    package_show = (fixtures_dir / "package_show.json").read_text(encoding="utf-8")
    csv_bytes = (fixtures_dir / "population_sample.csv").read_bytes()
    distribution_url = json.loads(package_show)["result"]["resources"][0]["url"]
    respx.get(PACKAGE_SHOW).mock(return_value=httpx.Response(200, text=package_show))
    respx.get(distribution_url).mock(return_value=httpx.Response(200, content=csv_bytes, headers={"ETag": '"v1"'}))

    result = mloda.run_all([Feature("Einwohner", options={GovDataReader.__name__: SLUG})])
    assert result[0].num_rows == 1000


@pytest.mark.live
def test_live_end_to_end() -> None:
    result = mloda.run_all(
        [Feature("Einwohner", options={GovDataReader.__name__: SLUG})],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert table.num_rows > 20_000
    assert table.schema.field("Einwohner").type == pa.int64()


@respx.mock
def test_elections_reader_level2(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BundeswahlleiterinReader, "cache_dir", str(tmp_path))
    kerg_bytes = (fixtures_dir / "kerg_sample.csv").read_bytes()
    respx.get(KERG_URL).mock(return_value=httpx.Response(200, content=kerg_bytes, headers={"ETag": '"k1"'}))
    result = mloda.run_all(
        [
            Feature("Gebiet", options={BundeswahlleiterinReader.__name__: KERG_URL}),
            Feature(KERG_MEASURE, options={BundeswahlleiterinReader.__name__: KERG_URL}),
        ],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert set(table.schema.names) == {"Gebiet", KERG_MEASURE}
    assert table.num_rows == 16
    assert table.column("Gebiet").to_pylist()[0] == "Flensburg – Schleswig"
    assert table.schema.field(KERG_MEASURE).type == pa.int64()


@pytest.mark.live
def test_elections_live_end_to_end() -> None:
    result = mloda.run_all(
        [Feature("Gebiet", options={BundeswahlleiterinReader.__name__: KERG_URL})],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert table.num_rows > 300
    assert table.column("Gebiet").to_pylist()[-1] == "Bundesgebiet"


def test_berlin_url_is_a_direct_distribution() -> None:
    locator = GovDataLocator.from_string(BERLIN_URL)
    assert locator.distribution_url == BERLIN_URL
    assert locator.dataset_id is None


@respx.mock
def test_berlin_wahl_reader_level2(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The Berlin single-header export needs no code change: only geometry options.
    monkeypatch.setattr(BundeswahlleiterinReader, "cache_dir", str(tmp_path))
    berlin_bytes = (fixtures_dir / "berlin_wahl_sample.csv").read_bytes()
    respx.get(BERLIN_URL).mock(return_value=httpx.Response(200, content=berlin_bytes, headers={"ETag": '"b1"'}))
    result = mloda.run_all(
        [
            Feature("Bezirksname", options=dict(BERLIN_OPTIONS)),
            Feature("Gueltig", options=dict(BERLIN_OPTIONS)),
            Feature("P02", options=dict(BERLIN_OPTIONS)),
        ],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert set(table.schema.names) == {"Bezirksname", "Gueltig", "P02"}
    assert table.num_rows == 12
    assert table.column("Bezirksname").to_pylist()[0] == "Mitte"
    assert table.schema.field("Gueltig").type == pa.float64()
    assert table.column("Gueltig").to_pylist()[0] == 428.0
    assert table.column("P02").to_pylist()[0] == 102.0


@respx.mock
def test_geometry_options_default_to_btw25(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BundeswahlleiterinReader, "cache_dir", str(tmp_path))
    kerg_bytes = (fixtures_dir / "kerg_sample.csv").read_bytes()
    respx.get(KERG_URL).mock(return_value=httpx.Response(200, content=kerg_bytes, headers={"ETag": '"k1"'}))
    explicit_btw25: dict[str, object] = {
        BundeswahlleiterinReader.__name__: KERG_URL,
        OPTION_WAHL_SKIPROWS: 5,
        OPTION_WAHL_HEADER_ROWS: 3,
        OPTION_WAHL_LABEL_COLUMNS: 4,
        OPTION_WAHL_VALUE_TYPE: "integer",
    }
    defaulted = mloda.run_all(
        [Feature("Gebiet", options={BundeswahlleiterinReader.__name__: KERG_URL})],
        compute_frameworks=["PyArrowTable"],
    )[0]
    explicit = mloda.run_all(
        [Feature("Gebiet", options=explicit_btw25)],
        compute_frameworks=["PyArrowTable"],
    )[0]
    assert defaulted.equals(explicit)


def test_bad_geometry_option_raises(fixtures_dir: Path) -> None:
    locator = GovDataLocator.from_string(KERG_URL)
    distribution = ResolvedDistribution(url=KERG_URL, license=None, dataset=None)
    options = Options({OPTION_WAHL_SKIPROWS: "five"})
    with pytest.raises(ValueError):
        BundeswahlleiterinReader._parse(fixtures_dir / "kerg_sample.csv", locator, distribution, options)


@pytest.mark.live
def test_berlin_wahl_live_end_to_end() -> None:
    result = mloda.run_all(
        [
            Feature("Bezirksname", options=dict(BERLIN_OPTIONS)),
            Feature("Gueltig", options=dict(BERLIN_OPTIONS)),
        ],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert table.num_rows > 3000
    assert "Mitte" in table.column("Bezirksname").to_pylist()
