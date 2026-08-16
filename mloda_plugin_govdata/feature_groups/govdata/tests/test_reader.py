"""Level 2 (recorded) and Level 3 (live) tests for the GovData reader."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, cast

import httpx
import pyarrow as pa
import pytest
import respx
from mloda.provider import FeatureSet
from mloda.user import Feature, Options, mloda
from mloda_plugins.feature_group.input_data.read_file import ReadFile

from mloda_plugin_govdata.feature_groups.govdata.bundeswahlleiterin import (
    OPTION_WAHL_HEADER_ROWS,
    OPTION_WAHL_LABEL_COLUMNS,
    OPTION_WAHL_SKIPROWS,
    OPTION_WAHL_VALUE_TYPE,
    BundeswahlleiterinReader,
)
from mloda_plugin_govdata.feature_groups.govdata.core.client import build_client
from mloda_plugin_govdata.feature_groups.govdata.core.locator import GovDataLocator
from mloda_plugin_govdata.feature_groups.govdata.core.parse import parse_german_csv
from mloda_plugin_govdata.feature_groups.govdata.core.provenance import FetchedPayload, Provenance
from mloda_plugin_govdata.feature_groups.govdata.feature import GovDataFeature
from mloda_plugin_govdata.feature_groups.govdata.population import StuttgartPopulationReader
from mloda_plugin_govdata.feature_groups.govdata.reader import BaseGovDataReader, GovDataReader
from mloda_plugin_govdata.feature_groups.govdata.uba import UbaAirReader, uba_measures_url

SLUG = "einwohner-nach-altersgruppen-und-stadtbezirken"
PACKAGE_SHOW = "https://ckan.govdata.de/api/3/action/package_show"
KERG_URL = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv"
KERG_MEASURE = "Wahlberechtigte Erststimmen Endgültig"
BERLIN_URL = "https://www.wahlen-berlin.de/wahlen/BE2023/AFSPRAES/agh/Datenexport_AGH2023_Zweitstimme_W_BE.csv"
# The wahlen-berlin.de Datenexport geometry: no preamble, one header row, 12 label
# columns (Adresse..Zeit), then vote counts and German-decimal percentage columns.
BERLIN_OPTIONS: dict[str, Any] = {
    BundeswahlleiterinReader.__name__: BERLIN_URL,
    OPTION_WAHL_SKIPROWS: 0,
    OPTION_WAHL_HEADER_ROWS: 1,
    OPTION_WAHL_LABEL_COLUMNS: 12,
    OPTION_WAHL_VALUE_TYPE: "float",
}


def _mock_population_endpoints(fixtures_dir: Path) -> None:
    package_show = (fixtures_dir / "package_show.json").read_text(encoding="utf-8")
    csv_bytes = (fixtures_dir / "population_sample.csv").read_bytes()
    distribution_url = json.loads(package_show)["result"]["resources"][0]["url"]
    respx.get(PACKAGE_SHOW).mock(return_value=httpx.Response(200, text=package_show))
    respx.get(distribution_url).mock(return_value=httpx.Response(200, content=csv_bytes, headers={"ETag": '"v1"'}))


class _FakeFeatureSet:
    """Just enough FeatureSet surface for load_data; mirrors the sorted-tuple contract."""

    def __init__(self, names: set[str], options: Options | None = None) -> None:
        self._names = tuple(sorted(names))
        self.options = options  # FeatureSet leaves this None until a feature is added

    def get_all_names(self) -> tuple[str, ...]:
        return self._names


@dataclass(frozen=True)
class _FakeLocator:
    """Throwaway second locator type; proves the reader is generic over its locator."""

    code: str

    def describe(self) -> str:
        return f"fake:{self.code}"

    @classmethod
    def coerce(cls, value: object) -> "_FakeLocator | None":
        return cls(value) if isinstance(value, str) and value else None


class FakeReader(BaseGovDataReader[_FakeLocator]):
    """Reads from a locator the base class knows nothing about, proving _fetch is a real seam."""

    seen_provenance: ClassVar[list[Provenance]] = []

    @classmethod
    def locator_type(cls) -> type[_FakeLocator]:
        return _FakeLocator

    @classmethod
    def _fetch(cls, locator: _FakeLocator, client: httpx.Client) -> FetchedPayload:
        path = Path(cls.cache_dir) / f"{locator.code}.csv"
        path.write_text("a;b\n1;2\n", encoding="utf-8")
        return FetchedPayload(
            path=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            retrieved_at=datetime.now(timezone.utc),
            provenance=Provenance(source="fake", url=locator.describe()),
        )

    @classmethod
    def _parse(
        cls, path: Path, locator: _FakeLocator, provenance: Provenance, options: Options | None = None
    ) -> pa.Table:
        cls.seen_provenance.append(provenance)
        return parse_german_csv(path, None)


def test_feature_group_uses_base_govdata_reader() -> None:
    assert isinstance(GovDataFeature.input_data(), BaseGovDataReader)


def test_class_options_key_normalizes_to_reader_name() -> None:
    # The reader class works as an options key; it normalizes to the class-name string (mloda >=0.10.0).
    # The cast bridges a 0.10.0 typing gap: the runtime accepts class keys, the hints only admit str.
    options = Options(cast(dict[str, Any], {GovDataReader: SLUG}))
    assert options.get(GovDataReader.__name__) == SLUG


@respx.mock
def test_load_data_level2(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StuttgartPopulationReader, "cache_dir", str(tmp_path))
    package_show = (fixtures_dir / "package_show.json").read_text(encoding="utf-8")
    csv_bytes = (fixtures_dir / "population_sample.csv").read_bytes()
    distribution_url = json.loads(package_show)["result"]["resources"][0]["url"]

    respx.get(PACKAGE_SHOW).mock(return_value=httpx.Response(200, text=package_show))
    respx.get(distribution_url).mock(return_value=httpx.Response(200, content=csv_bytes, headers={"ETag": '"v1"'}))

    result = mloda.run_all(
        [
            Feature("Einwohner", options={StuttgartPopulationReader.__name__: SLUG}),
            Feature("Stadtbezirk", options={StuttgartPopulationReader.__name__: SLUG}),
        ],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert set(table.schema.names) == {"Einwohner", "Stadtbezirk"}
    assert table.num_rows == 1000
    assert table.schema.field("Einwohner").type == pa.int64()
    # RunResult.plan (mloda >=0.10.0): the resolved execution steps name our group and framework.
    compute_steps = [step for step in result.plan if step.step_kind == "compute"]
    assert [step.feature_group_name for step in compute_steps] == ["GovDataFeature"]
    assert compute_steps[0].compute_framework_name == "PyArrowTable"
    assert set(compute_steps[0].requested_feature_names) == {"Einwohner", "Stadtbezirk"}


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
        [Feature("Einwohner", options={StuttgartPopulationReader.__name__: SLUG})],
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
    explicit_btw25: dict[str, Any] = {
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
    provenance = Provenance(source="url", url=KERG_URL)
    options = Options({OPTION_WAHL_SKIPROWS: "five"})
    with pytest.raises(ValueError):
        BundeswahlleiterinReader._parse(fixtures_dir / "kerg_sample.csv", locator, provenance, options)


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


@respx.mock
def test_peek_population_level2(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StuttgartPopulationReader, "cache_dir", str(tmp_path))
    _mock_population_endpoints(fixtures_dir)
    assert StuttgartPopulationReader.peek(SLUG) == {
        "Stichtag": "date32[day]",
        "Stadtbezirk": "string",
        "Alter in 10 Gruppen": "string",
        "Einwohner": "int64",
    }


@respx.mock
def test_generic_reader_reads_unknown_dataset_as_strings(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The generic reader carries no dataset schema; every column comes back as a string.
    monkeypatch.setattr(GovDataReader, "cache_dir", str(tmp_path))
    _mock_population_endpoints(fixtures_dir)
    assert GovDataReader.peek(SLUG) == {
        "Stichtag": "string",
        "Stadtbezirk": "string",
        "Alter in 10 Gruppen": "string",
        "Einwohner": "string",
    }


@respx.mock
def test_peek_elections_level2(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BundeswahlleiterinReader, "cache_dir", str(tmp_path))
    kerg_bytes = (fixtures_dir / "kerg_sample.csv").read_bytes()
    respx.get(KERG_URL).mock(return_value=httpx.Response(200, content=kerg_bytes, headers={"ETag": '"k1"'}))
    columns = BundeswahlleiterinReader.peek(KERG_URL)
    assert columns["Gebiet"] == "string"
    assert columns[KERG_MEASURE] == "int64"


@respx.mock
def test_peek_uba_level2(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(UbaAirReader, "cache_dir", str(tmp_path))
    url = uba_measures_url(station=143, component=3, scope=2, date_from="2025-01-01", date_to="2025-01-01")
    payload = (fixtures_dir / "uba_measures.json").read_bytes()
    respx.get(url).mock(return_value=httpx.Response(200, content=payload, headers={"ETag": '"u1"'}))
    columns = UbaAirReader.peek(url)
    assert columns["station_id"] == "int64"
    assert columns["value"] == "double"


def test_peek_rejects_unusable_data_access() -> None:
    with pytest.raises(ValueError, match="cannot handle data access"):
        GovDataReader.peek(123)


@pytest.mark.parametrize(
    "reader",
    [BaseGovDataReader, GovDataReader, StuttgartPopulationReader, BundeswahlleiterinReader, UbaAirReader, FakeReader],
)
def test_readers_classify_as_final_readers(reader: type[BaseGovDataReader[Any]]) -> None:
    # mloda >=0.10.0 classifies readers structurally: overriding load_data wholesale
    # relative to the ReadFile anchor makes each reader final; the ReadFile base is not.
    assert reader.final_reader_anchor() is ReadFile
    assert reader.is_final_reader() is True
    assert ReadFile.is_final_reader() is False


@respx.mock
def test_unknown_feature_names_available_columns(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GovDataReader, "cache_dir", str(tmp_path))
    _mock_population_endpoints(fixtures_dir)
    features = cast(FeatureSet, _FakeFeatureSet({"Einwohner_", "Stadtbezirk"}))
    with pytest.raises(ValueError) as excinfo:
        GovDataReader.load_data(SLUG, features)
    message = str(excinfo.value)
    assert "Unknown feature(s) 'Einwohner_'" in message
    assert "Available: Alter in 10 Gruppen, Einwohner, Stadtbezirk, Stichtag." in message
    assert "Did you mean 'Einwohner' instead of 'Einwohner_'?" in message


@respx.mock
def test_unknown_feature_suggestion_only_for_close_matches(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GovDataReader, "cache_dir", str(tmp_path))
    _mock_population_endpoints(fixtures_dir)
    features = cast(FeatureSet, _FakeFeatureSet({"Einwohner_", "zzzzz"}))
    with pytest.raises(ValueError) as excinfo:
        GovDataReader.load_data(SLUG, features)
    message = str(excinfo.value)
    assert "Unknown feature(s) 'Einwohner_', 'zzzzz'" in message
    assert message.count("Did you mean") == 1  # no suggestion for 'zzzzz'
    assert "Did you mean 'Einwohner' instead of 'Einwohner_'?" in message


def test_fake_reader_option_never_yields_govdata_locator() -> None:
    fake_locator = FakeReader.match_subclass_data_access("x", ["a"], Options({}))
    assert fake_locator == _FakeLocator("x")
    assert not isinstance(fake_locator, GovDataLocator)
    assert FakeReader._coerce_locator("x") == _FakeLocator("x")
    assert FakeReader.match_subclass_data_access(123, ["a"], Options({})) is None
    assert isinstance(GovDataReader.match_subclass_data_access("x", ["a"], Options({})), GovDataLocator)
    assert FakeReader.match_subclass_data_access(_FakeLocator("x"), ["a"], Options({})) == _FakeLocator("x")
    assert FakeReader._coerce_locator(_FakeLocator("x")) == _FakeLocator("x")


@respx.mock
def test_fake_reader_end_to_end_makes_no_http_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeReader, "cache_dir", str(tmp_path))
    FakeReader.seen_provenance.clear()
    result = mloda.run_all(
        [Feature("a", options={FakeReader.__name__: "x"})],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert table.column("a").to_pylist() == ["1"]
    assert respx.calls.call_count == 0
    assert FakeReader.seen_provenance == [Provenance(source="fake", url="fake:x")]


@respx.mock
def test_unknown_feature_message_uses_locator_describe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeReader, "cache_dir", str(tmp_path))
    features = cast(FeatureSet, _FakeFeatureSet({"zz"}))
    with pytest.raises(ValueError) as excinfo:
        FakeReader.load_data("x", features)
    message = str(excinfo.value)
    assert "'fake:x'" in message
    assert "Available: a, b." in message


def test_base_reader_declines_unusable_data_access() -> None:
    assert BaseGovDataReader.match_subclass_data_access(object(), ["a"], Options({})) is None
    assert isinstance(BaseGovDataReader.match_subclass_data_access(SLUG, ["a"], Options({})), GovDataLocator)


@respx.mock
def test_fetch_returns_payload_with_provenance(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GovDataReader, "cache_dir", str(tmp_path))
    _mock_population_endpoints(fixtures_dir)
    with build_client() as client:
        payload = GovDataReader._fetch(GovDataLocator(dataset_id=SLUG), client)
    assert payload.path.exists()
    assert payload.sha256 == hashlib.sha256(payload.path.read_bytes()).hexdigest()
    assert payload.provenance.source == "ckan"
    assert payload.provenance.license == "CC-BY-4.0"
    assert payload.provenance.dataset is not None
    assert payload.retrieved_at.tzinfo is not None


@respx.mock
def test_base_fetch_rejects_foreign_locator() -> None:
    with build_client() as client, pytest.raises(NotImplementedError):
        BaseGovDataReader._fetch(_FakeLocator("x"), client)
