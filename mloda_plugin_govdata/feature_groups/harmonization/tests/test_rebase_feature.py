"""KreisRebaseFeature: matching, option forwarding, and the C2 cells through mloda.run_all."""

import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
import respx
from mloda.user import Feature, FeatureName, Options, mloda

from mloda_plugin_govdata.feature_groups.destatis.core.auth import OPTION_GENESIS_CREDENTIALS, DestatisCredentials
from mloda_plugin_govdata.feature_groups.destatis.reader import DestatisReader
from mloda_plugin_govdata.feature_groups.govdata.core.cache import CacheMissError
from mloda_plugin_govdata.feature_groups.harmonization.rebase import PARTS, KreisRebaseFeature
from mloda_plugin_govdata.harmonization.rebase import Flag, ShareKind, rebase

from .conftest import COCHEM_ZELL_ZIP, EXTRACT, GOETTINGEN_LOCATOR, GOETTINGEN_ZIP, LAND_ZIP

D1_NAME = "destatis__bevoelkerung__kreise"
YEARS = {"rebase_from_year": 2015, "rebase_to_year": 2016}


def _expected(path: Path) -> list[tuple[str, int, int, str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [(r["key"], int(r["year"]), int(r["value"]), r["flag"], r["sources"]) for r in csv.DictReader(handle)]


def _cells(table: pa.Table, name: str) -> list[tuple[str, int, int, str, str]]:
    columns = [table.column(f"{name}~{part}").to_pylist() for part in ("key", "year", "value", "flag", "sources")]
    return [(key, year, round(value), flag, sources) for key, year, value, flag, sources in zip(*columns)]


def _run(features: list[Feature | str]) -> Any:
    return mloda.run_all(features, compute_frameworks=["PyArrowTable"])


# --- Level 1: matching and input features -----------------------------------------------------


def test_matches_the_chained_name_and_the_configured_d1_name() -> None:
    assert KreisRebaseFeature.match_feature_group_criteria("value__rebased", Options({}))
    assert KreisRebaseFeature.match_feature_group_criteria("value__rebased~flag", Options({}))
    assert not KreisRebaseFeature.match_feature_group_criteria("value", Options({}))
    configured = Options(group=YEARS, context={"in_features": "value"})
    assert KreisRebaseFeature.match_feature_group_criteria(D1_NAME, configured)
    assert not KreisRebaseFeature.match_feature_group_criteria(D1_NAME, Options(context={"in_features": "value"}))
    assert not KreisRebaseFeature.match_feature_group_criteria(D1_NAME, Options(group=YEARS))


def test_children_carry_the_locator_and_leave_the_group_keys_behind() -> None:
    options = Options(group={DestatisReader.__name__: GOETTINGEN_LOCATOR, **YEARS})
    children = KreisRebaseFeature().input_features(options, FeatureName("value__rebased")) or set()
    assert {str(c.name) for c in children} == {
        "value",
        "1_variable_code",
        "1_variable_attribute_code",
        "time",
        "value_marker",
    }
    for child in children:
        assert child.forward_group is None  # the reader locator forwards by default
        assert {"rebase_from_year", "rebase_to_year", "rebase_share"} <= child.forward_group_exclude
        assert child.inherit_context_keys == frozenset({OPTION_GENESIS_CREDENTIALS})
    configured = Options(group=YEARS, context={"in_features": "value"})
    assert {str(c.name) for c in KreisRebaseFeature().input_features(configured, FeatureName(D1_NAME)) or set()} == {
        "value",
        "1_variable_code",
        "1_variable_attribute_code",
        "time",
        "value_marker",
    }


def test_the_destatis_reader_leaves_chained_names_to_the_derived_groups() -> None:
    assert DestatisReader.match_subclass_data_access("12411-0015", ["value__rebased"], Options({})) is None
    assert DestatisReader.match_subclass_data_access("12411-0015", ["value"], Options({})) is not None


# --- Level 3: through mloda.run_all over the captured tables -------------------------------------


@respx.mock
def test_c2_goettingen_series_through_the_d1_name(
    genesis: Callable[[str], respx.Route], extract_keys: None, expected_dir: Path
) -> None:
    route = genesis(GOETTINGEN_ZIP)
    feature = Feature(
        D1_NAME,
        Options(group={DestatisReader.__name__: GOETTINGEN_LOCATOR, **YEARS}, context={"in_features": "value"}),
    )
    result = _run([feature])
    table = result[0]

    assert sorted(table.schema.names) == sorted(f"{D1_NAME}~{part}" for part in PARTS)
    assert _cells(table, D1_NAME) == _expected(expected_dir / "c2-goettingen-2016.csv")
    assert table.column(f"{D1_NAME}~value").to_pylist() == [322616.0, 324013.0, 329538.0, 327065.0, 328036.0]
    assert table.column(f"{D1_NAME}~marker").to_pylist() == [""] * 5
    assert route.calls.call_count == 1
    steps = [step.feature_group_name for step in result.plan if step.step_kind == "compute"]
    assert steps == ["GovDataFeature", "KreisRebaseFeature"]


@respx.mock
def test_the_chained_name_gives_the_same_rows(
    genesis: Callable[[str], respx.Route], extract_keys: None, expected_dir: Path
) -> None:
    genesis(GOETTINGEN_ZIP)
    table = _run([Feature("value__rebased", options={DestatisReader.__name__: GOETTINGEN_LOCATOR, **YEARS})])[0]
    assert _cells(table, "value__rebased") == _expected(expected_dir / "c2-goettingen-2016.csv")


@respx.mock
def test_one_sub_column_can_be_requested_alone(genesis: Callable[[str], respx.Route], extract_keys: None) -> None:
    genesis(GOETTINGEN_ZIP)
    table = _run([Feature("value__rebased~flag", options={DestatisReader.__name__: GOETTINGEN_LOCATOR, **YEARS})])[0]
    assert table.schema.names == ["value__rebased~flag"]
    assert table.column(0).to_pylist() == [Flag.REBASED.value] * 3 + [Flag.OBSERVED.value] * 2


@respx.mock
def test_issues_sit_next_to_their_rows_and_the_edition_carries_the_rest(
    genesis: Callable[[str], respx.Route], extract_keys: None
) -> None:
    genesis(GOETTINGEN_ZIP)
    table = _run([Feature("value__rebased", options={DestatisReader.__name__: GOETTINGEN_LOCATOR, **YEARS})])[0]
    issues = dict(
        zip(table.column("value__rebased~year").to_pylist(), table.column("value__rebased~issues").to_pylist())
    )

    assert "not_applicable: 03159 does not exist before 31.12.2016" in issues[2013]
    assert "unverified_year" in issues[2014] and "03152" in issues[2014] and "03156" in issues[2014]
    assert issues[2016] == ""
    assert issues[2017].startswith("unverified_year: no key sheet 2016-2017")

    editions = set(table.column("value__rebased~edition").to_pylist())
    assert len(editions) == 1
    edition = json.loads(editions.pop())
    assert edition["source"] == EXTRACT.name
    assert edition["sha256"] == EXTRACT.sha256
    assert (edition["sheet"], edition["share"], edition["census_breaks"]) == ("2015-2016", "population", [])
    # Issues on keys no output row carries are kept as kind to keys, never dropped.
    assert edition["issues_elsewhere"] == {"not_applicable": ["03152", "03156"], "share_sum": ["07135", "07137"]}


@respx.mock
def test_the_fractional_case_matches_the_expected_values(
    genesis: Callable[[str], respx.Route], extract_keys: None, expected_dir: Path
) -> None:
    genesis(COCHEM_ZELL_ZIP)
    options = {
        DestatisReader.__name__: {
            "name": "12411-0015",
            "regionalvariable": "KREISE",
            "startyear": 2013,
            "endyear": 2014,
        },
        "rebase_from_year": 2013,
        "rebase_to_year": 2014,
        "rebase_share": ShareKind.POPULATION.value,
    }
    table = _run([Feature("value__rebased", options=options)])[0]
    assert _cells(table, "value__rebased") == _expected(expected_dir / "c2-cochem-zell-2014.csv")
    assert set(table.column("value__rebased~issues").to_pylist()) == {""}


@respx.mock
def test_options_reach_the_module(
    genesis: Callable[[str], respx.Route], extract_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    genesis(GOETTINGEN_ZIP)
    seen: dict[str, Any] = {}

    def spy(observations: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return rebase(observations, **kwargs)

    monkeypatch.setattr("mloda_plugin_govdata.feature_groups.harmonization.rebase.rebase", spy)
    options = {
        DestatisReader.__name__: GOETTINGEN_LOCATOR,
        **YEARS,
        "rebase_share": "area",
        "rebase_tolerance": 1e-3,
        "rebase_on_unmatched": "flag",
        "rebase_on_incomplete": "drop",
    }
    _run([Feature("value__rebased", options=options)])
    assert seen["source"] is EXTRACT
    assert (seen["from_year"], seen["to_year"], seen["share"], seen["tolerance"]) == (2015, 2016, "area", 1e-3)
    assert (seen["on_unmatched"], seen["on_incomplete"]) == ("flag", "drop")


@respx.mock
def test_explicit_credentials_travel_from_the_derived_feature_to_the_reader(
    genesis: Callable[[str], respx.Route], extract_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    route = genesis(GOETTINGEN_ZIP)
    for var in ("GENESIS_TOKEN", "GENESIS_USER", "GENESIS_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    feature = Feature(
        "value__rebased",
        Options(
            group={DestatisReader.__name__: GOETTINGEN_LOCATOR, **YEARS},
            context={OPTION_GENESIS_CREDENTIALS: DestatisCredentials(token="explicit-token")},
        ),
    )
    table = _run([feature])[0]
    assert table.num_rows == 5
    assert route.calls.call_count == 1


@respx.mock
def test_missing_years_raise_a_clear_error(genesis: Callable[[str], respx.Route], extract_keys: None) -> None:
    genesis(GOETTINGEN_ZIP)
    with pytest.raises(ValueError, match="rebase_from_year and rebase_to_year"):
        _run([Feature("value__rebased", options={DestatisReader.__name__: GOETTINGEN_LOCATOR})])


@respx.mock
def test_a_land_table_is_refused_by_its_variable(genesis: Callable[[str], respx.Route], extract_keys: None) -> None:
    genesis(LAND_ZIP)
    locator = {"name": "12411-0010", "startyear": 2024, "endyear": 2024}
    with pytest.raises(ValueError, match=r"variable block 1 holds \['DLAND'\], not 'KREISE'"):
        _run([Feature("value__rebased", options={DestatisReader.__name__: locator, **YEARS})])


def test_keys_missing_from_the_cache_name_the_fetch_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(KreisRebaseFeature, "cache_dir", str(tmp_path))
    with pytest.raises(CacheMissError, match="load_bbsr_kreise\\(cache, revalidate=True\\)"):
        KreisRebaseFeature.load_keys()
