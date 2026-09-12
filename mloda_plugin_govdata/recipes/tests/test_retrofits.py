"""The three M1 retrofits run offline through mloda, each with its zero-vs-missing case."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pyarrow as pa
import respx

from mloda_plugin_govdata.recipes import load_recipe

from .conftest import GOVDATA_FIXTURES, Mock, run
from .shipped import (
    BUNDESTAGSWAHL_2025,
    CSU_ZWEITSTIMMEN,
    STUTTGART_POPULATION,
    UBA_OZONE_STATION_143,
    UEBRIGE_VORPERIODE,
)

STUTTGART_HEADER = "Stichtag;Stadtbezirk;Alter in 10 Gruppen;Einwohner\n"


@respx.mock
def test_stuttgart_population_runs(recipes_dir: Path, stuttgart: Mock) -> None:
    stuttgart()
    recipe = load_recipe(recipes_dir / STUTTGART_POPULATION.file)
    table = run(recipe.features)[0]
    assert table.num_rows == 1000
    assert table.schema.field("Stichtag").type == pa.date32()
    assert table.schema.field("Einwohner").type == pa.int64()
    assert table.column("Stichtag").to_pylist()[0] == date(1986, 6, 30)
    assert recipe.compliance.sources[0].credential_env == []


@respx.mock
def test_stuttgart_zero_vs_missing_an_empty_cell_is_null_and_0_is_zero(recipes_dir: Path, stuttgart: Mock) -> None:
    rows = "30.06.1986;Mitte;0 bis unter 3 Jahre;\n30.06.1986;Mitte;3 bis unter 6 Jahre;0\n"
    stuttgart((STUTTGART_HEADER + rows).encode("utf-8"))
    table = run(load_recipe(recipes_dir / STUTTGART_POPULATION.file).features)[0]
    assert table.column("Einwohner").to_pylist() == [None, 0]


@respx.mock
def test_bundestagswahl_runs(recipes_dir: Path, kerg: Mock) -> None:
    kerg()
    recipe = load_recipe(recipes_dir / BUNDESTAGSWAHL_2025.file)
    table = run(recipe.features)[0]
    assert table.num_rows == 31
    assert table.schema.field("Nr").type == pa.string()
    assert table.schema.field("Wahlberechtigte Erststimmen Endgültig").type == pa.int64()
    assert table.column("Nr").to_pylist()[0] == "001"
    assert recipe.compliance.sources[0].credential_env == []


@respx.mock
def test_bundestagswahl_zero_vs_missing_not_on_the_ballot_is_null_and_no_others_is_0(
    recipes_dir: Path, kerg: Mock
) -> None:
    kerg()
    table = run(load_recipe(recipes_dir / BUNDESTAGSWAHL_2025.file).features)[0]
    csu = dict(zip(table.column("Nr").to_pylist(), table.column(CSU_ZWEITSTIMMEN).to_pylist()))
    assert csu["09"] > 0 and csu["01"] is None
    assert 0 in table.column(UEBRIGE_VORPERIODE).to_pylist()
    assert table.column(UEBRIGE_VORPERIODE).null_count == 0


def test_uba_ozone_pins_the_captured_reply(recipes_dir: Path) -> None:
    (source,) = load_recipe(recipes_dir / UBA_OZONE_STATION_143.file).compliance.sources
    assert source.sha256 == hashlib.sha256((GOVDATA_FIXTURES / "uba_measures.json").read_bytes()).hexdigest()


@respx.mock
def test_uba_ozone_runs(recipes_dir: Path, uba: Mock) -> None:
    uba()
    recipe = load_recipe(recipes_dir / UBA_OZONE_STATION_143.file)
    table = run(recipe.features)[0]
    assert table.num_rows == 24
    assert table.schema.field("value").type == pa.float64()
    assert table.column("station_id").to_pylist() == [143] * 24
    assert table.column("value").to_pylist()[0] == 37.0
    assert recipe.compliance.sources[0].credential_env == []


@respx.mock
def test_uba_zero_vs_missing_a_null_leaf_is_null_and_0_is_zero(recipes_dir: Path, uba: Mock) -> None:
    payload = json.loads((GOVDATA_FIXTURES / "uba_measures.json").read_text(encoding="utf-8"))
    series = payload["data"]["143"]
    series["2025-01-01 00:00:00"][2] = None
    series["2025-01-01 01:00:00"][2] = 0
    uba(json.dumps(payload).encode("utf-8"))
    table = run(load_recipe(recipes_dir / UBA_OZONE_STATION_143.file).features)[0]
    assert table.column("value").to_pylist()[:3] == [None, 0.0, 35.0]
