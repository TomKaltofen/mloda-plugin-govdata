"""AgsToNutsFeature: matching, the explicit edition, and the mapping through mloda.run_all."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import respx
from mloda.provider import FeatureChainParser
from mloda.user import Feature, FeatureName, Options, mloda

from mloda_plugin_govdata.feature_groups.destatis.core.auth import OPTION_GENESIS_CREDENTIALS
from mloda_plugin_govdata.feature_groups.destatis.reader import DestatisReader
from mloda_plugin_govdata.feature_groups.govdata.core.cache import CacheMissError
from mloda_plugin_govdata.feature_groups.harmonization.base import PART_PATTERN
from mloda_plugin_govdata.feature_groups.harmonization.core.edition import Edition
from mloda_plugin_govdata.feature_groups.harmonization.core.nuts import UnmatchedKeysError
from mloda_plugin_govdata.feature_groups.harmonization.nuts import NULL_KEY, PARTS, AgsToNutsFeature

from .conftest import (
    GOETTINGEN_LOCATOR,
    GOETTINGEN_ZIP,
    LAND_ZIP,
    ffcsv_zip_with_rows,
    fixture_edition,
    gv_isys_changes,
    lau_rows,
)

KEY = "1_variable_attribute_code"
NAME = f"{KEY}__nuts2024"


def _run(features: list[Feature | str]) -> Any:
    return mloda.run_all(features, compute_frameworks=["PyArrowTable"])


def test_matches_only_the_pinned_edition() -> None:
    assert AgsToNutsFeature.match_feature_group_criteria(NAME, Options({}))
    assert AgsToNutsFeature.match_feature_group_criteria(f"{NAME}~nuts3", Options({}))
    assert not AgsToNutsFeature.match_feature_group_criteria(f"{KEY}__nuts2021", Options({}))
    assert AgsToNutsFeature.match_feature_group_criteria(
        "kreis_nuts", Options(group={"nuts_version": "2024"}, context={"in_features": KEY})
    )
    assert not AgsToNutsFeature.match_feature_group_criteria(
        "kreis_nuts", Options(group={"nuts_version": "2021"}, context={"in_features": KEY})
    )
    assert not AgsToNutsFeature.match_feature_group_criteria("kreis_nuts", Options(context={"in_features": KEY}))


def test_the_named_capture_binds_nuts_version_by_name() -> None:
    # Regression guard on the actual production pattern (fails against the old unnamed capture,
    # whose parsed value is positional only, not a name -> value binding).
    parsed = FeatureChainParser.parse_name(NAME, [AgsToNutsFeature.PREFIX_PATTERN])
    assert parsed.named_captures == {"nuts_version": "2024"}


def test_a_second_overlapping_nuts_version_would_still_bind_by_name() -> None:
    # A pattern with two alternatives, as a real second edition would add, still binds each value
    # by name unconditionally. No FeatureGroup involved: this exercises the parser directly, so it
    # can't leak a test-local subclass into mloda's global FeatureGroup discovery.
    pattern = rf".*__nuts(?P<nuts_version>2024|2021)(?:~{PART_PATTERN})?$"
    assert FeatureChainParser.parse_name(f"{KEY}__nuts2024", [pattern]).named_captures == {"nuts_version": "2024"}
    assert FeatureChainParser.parse_name(f"{KEY}__nuts2021", [pattern]).named_captures == {"nuts_version": "2021"}


def test_the_child_is_the_key_column_with_the_locator_forwarded() -> None:
    options = Options(group={DestatisReader.__name__: GOETTINGEN_LOCATOR, "nuts_on_unmatched": "flag"})
    (child,) = AgsToNutsFeature().input_features(options, FeatureName(NAME)) or set()
    assert str(child.name) == KEY
    assert child.forward_group is None
    assert child.forward_group_exclude == frozenset({"nuts_version", "nuts_on_unmatched", "in_features"})
    assert child.forward_group is None
    assert child.inherit_context_keys == frozenset({OPTION_GENESIS_CREDENTIALS})


@respx.mock
def test_kreis_keys_map_through_the_edition_and_its_history(
    genesis: Callable[[str], respx.Route], extract_edition: Edition
) -> None:
    genesis(GOETTINGEN_ZIP)
    features: list[Feature | str] = [
        Feature(KEY, options={DestatisReader.__name__: GOETTINGEN_LOCATOR}),
        Feature(NAME, options={DestatisReader.__name__: GOETTINGEN_LOCATOR}),
    ]
    frames = {name: table for table in _run(features) for name in table.schema.names}
    table = frames[f"{NAME}~key"]

    assert sorted(table.schema.names) == sorted(f"{NAME}~{part}" for part in PARTS)
    assert table.num_rows == 15  # row-aligned with the reader output, one frame per feature group
    assert table.column(f"{NAME}~key").to_pylist() == frames[KEY].column(KEY).to_pylist()
    assert set(table.column(f"{NAME}~nuts3").to_pylist()) == {"DE91C"}  # retired keys via the GV-ISys redirect
    assert set(table.column(f"{NAME}~nuts2").to_pylist()) == {"DE91"}
    assert set(table.column(f"{NAME}~nuts1").to_pylist()) == {"DE9"}
    assert set(table.column(f"{NAME}~version").to_pylist()) == {"2024"}
    assert set(table.column(f"{NAME}~unmatched").to_pylist()) == {""}


@respx.mock
def test_one_sub_column_and_the_configured_name(
    genesis: Callable[[str], respx.Route], extract_edition: Edition
) -> None:
    genesis(GOETTINGEN_ZIP)
    alone = _run([Feature(f"{NAME}~nuts3", options={DestatisReader.__name__: GOETTINGEN_LOCATOR})])[0]
    assert alone.schema.names == [f"{NAME}~nuts3"]
    configured = Feature(
        "destatis__kreise__nuts",
        Options(
            group={DestatisReader.__name__: GOETTINGEN_LOCATOR, "nuts_version": "2024"}, context={"in_features": KEY}
        ),
    )
    table = _run([configured])[0]
    assert sorted(table.schema.names) == sorted(f"destatis__kreise__nuts~{part}" for part in PARTS)
    assert set(table.column("destatis__kreise__nuts~nuts3").to_pylist()) == {"DE91C"}


@respx.mock
def test_unmatched_keys_raise_by_default_and_flag_on_request(
    genesis: Callable[[str], respx.Route], monkeypatch: pytest.MonkeyPatch, reference_fixtures_dir: Path
) -> None:
    genesis(GOETTINGEN_ZIP)
    bare = fixture_edition(reference_fixtures_dir, with_history=False)  # no redirect for the retired keys
    monkeypatch.setattr(AgsToNutsFeature, "edition", classmethod(lambda cls: bare))

    with pytest.raises(UnmatchedKeysError, match="03152"):
        _run([Feature(NAME, options={DestatisReader.__name__: GOETTINGEN_LOCATOR})])

    options = {DestatisReader.__name__: GOETTINGEN_LOCATOR, "nuts_on_unmatched": "flag"}
    table = _run([Feature(NAME, options=options)])[0]
    columns = [table.column(f"{NAME}~{part}").to_pylist() for part in ("key", "nuts3", "unmatched")]
    rows = {key: (nuts3, reason) for key, nuts3, reason in zip(*columns)}
    assert rows["03159"] == ("DE91C", "")
    assert rows["03152"][0] is None and "03152 not found" in rows["03152"][1]
    assert rows["03156"][0] is None and "03156 not found" in rows["03156"][1]


@respx.mock
def test_land_keys_are_out_of_scope_and_say_so(genesis: Callable[[str], respx.Route], extract_edition: Edition) -> None:
    genesis(LAND_ZIP)
    locator = {"name": "12411-0010", "startyear": 2024, "endyear": 2024}
    with pytest.raises(UnmatchedKeysError, match="Land mapping is out of scope"):
        _run([Feature(NAME, options={DestatisReader.__name__: locator})])


@respx.mock
def test_a_cached_edition_of_another_version_is_refused(
    genesis: Callable[[str], respx.Route], monkeypatch: pytest.MonkeyPatch, reference_fixtures_dir: Path
) -> None:
    genesis(GOETTINGEN_ZIP)
    other = Edition(**{**fixture_edition(reference_fixtures_dir).__dict__, "nuts_version": "2021"})
    monkeypatch.setattr(AgsToNutsFeature, "edition", classmethod(lambda cls: other))
    with pytest.raises(ValueError, match="asks for NUTS 2024, the cached edition is NUTS 2021"):
        _run([Feature(NAME, options={DestatisReader.__name__: GOETTINGEN_LOCATOR})])


def test_an_edition_missing_from_the_cache_names_the_fetch_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(AgsToNutsFeature, "cache_dir", str(tmp_path))
    with pytest.raises(CacheMissError, match="load_edition\\(cache, revalidate=True\\).*AgsToNutsFeature.cache_dir"):
        AgsToNutsFeature.edition()


@respx.mock
def test_two_parts_of_one_output_in_one_request(
    genesis: Callable[[str], respx.Route], extract_edition: Edition
) -> None:
    genesis(GOETTINGEN_ZIP)
    options = {DestatisReader.__name__: GOETTINGEN_LOCATOR}
    table = _run([Feature(f"{NAME}~nuts1", options=options), Feature(f"{NAME}~nuts3", options=options)])[0]
    assert sorted(table.schema.names) == [f"{NAME}~nuts1", f"{NAME}~nuts3"]
    assert table.num_rows == 15


@respx.mock
def test_the_real_edition_carries_the_pinned_history(
    genesis: Callable[[str], respx.Route], monkeypatch: pytest.MonkeyPatch, reference_fixtures_dir: Path, tmp_path: Path
) -> None:
    # Only the two fetch-and-verify loaders are replaced, so edition() itself assembles the history.
    rows, changes = lau_rows(reference_fixtures_dir), gv_isys_changes(reference_fixtures_dir)
    monkeypatch.setattr(
        "mloda_plugin_govdata.feature_groups.harmonization.core.edition.load_lau_nuts_de",
        lambda cache, **kw: list(rows),
    )
    monkeypatch.setattr(
        "mloda_plugin_govdata.feature_groups.harmonization.nuts.load_gv_isys_changes",
        lambda year, cache, **kw: list(changes) if year == 2016 else [],
    )
    monkeypatch.setattr(AgsToNutsFeature, "cache_dir", str(tmp_path))
    edition = AgsToNutsFeature.edition()
    assert (edition.nuts_version, edition.year_range) == ("2024", (2016, 2024))
    assert edition.gv_isys_changes == changes

    genesis(GOETTINGEN_ZIP)
    table = _run([Feature(NAME, options={DestatisReader.__name__: GOETTINGEN_LOCATOR})])[0]
    assert set(table.column(f"{NAME}~nuts3").to_pylist()) == {"DE91C"}


@respx.mock
def test_nuts_codes_for_the_rebased_keys(
    genesis: Callable[[str], respx.Route], extract_edition: Edition, extract_keys: None
) -> None:
    # A part of one output is a column another group can chain onto.
    genesis(GOETTINGEN_ZIP)
    name = "value__rebased~key__nuts2024"
    options = {DestatisReader.__name__: GOETTINGEN_LOCATOR, "rebase_from_year": 2015, "rebase_to_year": 2016}
    table = _run([Feature(name, options=options)])[0]
    assert sorted(table.schema.names) == sorted(f"{name}~{part}" for part in PARTS)
    assert table.column(f"{name}~key").to_pylist() == ["03159"] * 5
    assert set(table.column(f"{name}~nuts3").to_pylist()) == {"DE91C"}


@respx.mock
def test_a_non_string_key_column_is_refused_by_name(
    genesis: Callable[[str], respx.Route], extract_edition: Edition
) -> None:
    genesis(GOETTINGEN_ZIP)
    with pytest.raises(TypeError, match="time must be a string column of AGS keys"):
        _run([Feature("time__nuts2024", options={DestatisReader.__name__: GOETTINGEN_LOCATOR})])


@respx.mock
def test_null_key_cells_are_named_and_kept_only_on_request(
    genesis: Callable[[str | bytes], respx.Route], extract_edition: Edition, ffcsv_fixtures_dir: Path
) -> None:
    zip_bytes = (ffcsv_fixtures_dir / GOETTINGEN_ZIP).read_bytes()

    def blank_one_key(row: str) -> str:
        return row.replace(";03159;", ";;", 1) if "327065" in row else row

    genesis(ffcsv_zip_with_rows(zip_bytes, lambda row: True, edit=blank_one_key))
    with pytest.raises(ValueError, match=rf"{KEY}, row \d+: {NULL_KEY}"):
        _run([Feature(NAME, options={DestatisReader.__name__: GOETTINGEN_LOCATOR})])
    options = {DestatisReader.__name__: GOETTINGEN_LOCATOR, "nuts_on_unmatched": "flag"}
    table = _run([Feature(NAME, options=options)])[0]
    keys, nuts3, reasons = (table.column(f"{NAME}~{part}").to_pylist() for part in ("key", "nuts3", "unmatched"))
    (row,) = [i for i, key in enumerate(keys) if key is None]
    assert (nuts3[row], reasons[row]) == (None, NULL_KEY)
    assert nuts3.count("DE91C") == 14 and reasons.count("") == 14


@respx.mock
def test_a_contradicting_explicit_version_is_refused(
    genesis: Callable[[str], respx.Route], extract_edition: Edition
) -> None:
    genesis(GOETTINGEN_ZIP)
    options = {DestatisReader.__name__: GOETTINGEN_LOCATOR, "nuts_version": "2021"}
    with pytest.raises(ValueError, match="'2021' not found in mapping for 'nuts_version'"):
        _run([Feature(NAME, options=options)])
