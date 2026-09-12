"""AgsToNutsFeature: matching, the explicit edition, and the mapping through mloda.run_all."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import respx
from mloda.user import Feature, FeatureName, Options, mloda

from mloda_plugin_govdata.feature_groups.destatis.core.auth import OPTION_GENESIS_CREDENTIALS
from mloda_plugin_govdata.feature_groups.destatis.reader import DestatisReader
from mloda_plugin_govdata.feature_groups.govdata.core.cache import CacheMissError
from mloda_plugin_govdata.feature_groups.harmonization.nuts import PARTS, AgsToNutsFeature
from mloda_plugin_govdata.harmonization.edition import Edition
from mloda_plugin_govdata.harmonization.nuts import UnmatchedKeysError

from .conftest import GOETTINGEN_LOCATOR, GOETTINGEN_ZIP, LAND_ZIP, fixture_edition

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
    with pytest.raises(CacheMissError, match="load_edition\\(cache, revalidate=True\\)"):
        AgsToNutsFeature.edition()
