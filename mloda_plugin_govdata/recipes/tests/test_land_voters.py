"""Recipe 3: both sides run, their Land rows line up by AGS-2, and the join itself waits on mloda."""

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
import respx
from mloda.user import Feature

from mloda_plugin_govdata.harmonization.land_codes import LAND_NAMES, check_land_names
from mloda_plugin_govdata.harmonization.tests.test_land_codes import BUNDESGEBIET, BUNDESGEBIET_ROW
from mloda_plugin_govdata.recipes import LoadedRecipe, frames_by_column, load_recipe

from .conftest import FFCSV_FIXTURES, GOVDATA_FIXTURES, LAND_ZIP, Mock, run
from .shipped import CSU_ZWEITSTIMMEN, KEY, LAND_POPULATION_VOTERS, VOTERS

Genesis = Callable[[Mapping[str, str | bytes]], respx.Route]


def _load(recipes_dir: Path) -> LoadedRecipe:
    return load_recipe(recipes_dir / LAND_POPULATION_VOTERS.file)


def _land_rows(election: Any) -> dict[str, dict[str, Any]]:
    names = election.schema.names
    rows = [dict(zip(names, values)) for values in zip(*(election.column(n).to_pylist() for n in names))]
    return {row["Nr"]: row for row in rows if row["gehört zu"] == BUNDESGEBIET}


def test_the_recipe_pins_both_payloads_and_carries_the_link(recipes_dir: Path) -> None:
    recipe = _load(recipes_dir)
    destatis, election = recipe.compliance.sources
    assert destatis.sha256 == hashlib.sha256((FFCSV_FIXTURES / LAND_ZIP).read_bytes()).hexdigest()
    assert election.credential_env == []
    (link,) = recipe.links
    assert (link.left_index.index, link.right_index.index) == ((KEY,), ("Nr",))
    options = [feature.options.group for feature in recipe.features if isinstance(feature, Feature)]
    assert link.left_discriminator in options and link.right_discriminator in options


@respx.mock
def test_both_sides_run_and_the_land_rows_line_up_by_name(recipes_dir: Path, genesis: Genesis, kerg: Mock) -> None:
    genesis({"12411-0010": LAND_ZIP})
    kerg((GOVDATA_FIXTURES / "kerg_sample.csv").read_bytes() + BUNDESGEBIET_ROW)
    frames = frames_by_column(run(_load(recipes_dir).features))  # without the links: the join waits on mloda
    destatis, election = frames["value"], frames["Nr"]
    assert destatis.num_rows == 16
    check_land_names(zip(destatis.column(KEY).to_pylist(), destatis.column("1_variable_attribute_label").to_pylist()))
    land_rows = _land_rows(election)  # the Bundesgebiet row has no parent and stays out
    check_land_names((nr, row["Gebiet"]) for nr, row in land_rows.items())
    assert set(land_rows) == set(destatis.column(KEY).to_pylist()) == set(LAND_NAMES)
    assert all(row[VOTERS] > 0 for row in land_rows.values())


@pytest.mark.xfail(
    strict=True,
    raises=ValueError,
    reason="mloda 0.10: same-class link keys are injected into both sides, so each reader is asked for the other's key",
)
@respx.mock
def test_the_links_block_joins_the_two_sides(recipes_dir: Path, genesis: Genesis, kerg: Mock) -> None:
    genesis({"12411-0010": LAND_ZIP})
    kerg()
    recipe = _load(recipes_dir)
    result = run(recipe.features, recipe.links)
    assert [step.step_kind for step in result.plan].count("join") == 1


@respx.mock
def test_zero_vs_missing_an_absent_party_is_null_and_a_land_count_is_never_a_sign(
    recipes_dir: Path, genesis: Genesis, kerg: Mock
) -> None:
    genesis({"12411-0010": LAND_ZIP})
    kerg()
    frames = frames_by_column(run(_load(recipes_dir).features))
    land_rows = _land_rows(frames["Nr"])
    # The CSU stands in Bayern only: elsewhere its cell is empty, which is null, not a zero.
    assert land_rows["09"][CSU_ZWEITSTIMMEN] > 0
    assert {row[CSU_ZWEITSTIMMEN] for nr, row in land_rows.items() if nr != "09"} == {None}
    # The Land population cells are all numbers: no GENESIS sign, no null.
    destatis = frames["value"]
    assert set(destatis.column("value_marker").to_pylist()) == {""}
    assert destatis.column("value").null_count == 0 and min(destatis.column("value").to_pylist()) > 0
