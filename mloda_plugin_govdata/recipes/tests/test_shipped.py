"""Every shipped recipe file is the writer's output of its definition, loads back, keeps its locked plan, and pins a
real payload."""

import hashlib
from pathlib import Path

import pytest
import respx
from mloda.steward import check_plan_lock

from mloda_plugin_govdata.feature_groups.govdata import build_client
from mloda_plugin_govdata.feature_groups.govdata.core.discovery import CC_BY_4_0, DL_DE_BY_2_0
from mloda_plugin_govdata.feature_groups.govdata.uba import UBA_LICENSE
from mloda_plugin_govdata.feature_groups.harmonization.core.reference.sources import (
    BBSR_KREISE,
    EUROSTAT_LAU_NUTS,
    EUROSTAT_NUTS_CORRESPONDENCE,
    gv_isys_source,
)
from mloda_plugin_govdata.recipes import build_recipe, load_recipe, recipe_to_json
from scripts.write_recipes import (
    BUNDESTAGSWAHL_2025,
    RECIPES,
    STUTTGART_POPULATION,
    ShippedRecipe,
    lock_path,
    main,
    recipe_plan,
)

IDS = [r.file for r in RECIPES]
LICENSES = {CC_BY_4_0, DL_DE_BY_2_0, UBA_LICENSE}  # the labels readers declare


@pytest.mark.parametrize("shipped", RECIPES, ids=IDS)
def test_the_file_is_what_the_writer_produces(recipes_dir: Path, shipped: ShippedRecipe) -> None:
    # No env scrubbing here: a GENESIS credential configured on this machine is scanned against every file.
    expected = recipe_to_json(build_recipe(shipped.features, shipped.compliance, shipped.links))
    assert (recipes_dir / shipped.file).read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("shipped", RECIPES, ids=IDS)
def test_the_file_loads_with_its_compliance_complete(recipes_dir: Path, shipped: ShippedRecipe) -> None:
    loaded = load_recipe(recipes_dir / shipped.file)
    assert len(loaded.features) == len(shipped.features)
    assert len(loaded.links) == len(shipped.links)
    for source in loaded.compliance.sources:
        assert source.modifications, "every source lists what the reader changes"
        assert source.retrieved_at.tzinfo is not None
        assert source.license in LICENSES


def test_reference_sources_use_the_reader_license_labels() -> None:
    references = (BBSR_KREISE, EUROSTAT_LAU_NUTS, EUROSTAT_NUTS_CORRESPONDENCE, gv_isys_source(2016))
    assert {source.license for source in references} <= LICENSES


# No routes: resolving a plan must not reach the network.
@respx.mock
@pytest.mark.parametrize("shipped", RECIPES, ids=IDS)
def test_the_plan_matches_its_lock(recipes_dir: Path, shipped: ShippedRecipe) -> None:
    check_plan_lock(recipe_plan(load_recipe(recipes_dir / shipped.file)), lock_path(recipes_dir, shipped.file))


def _texts(directory: Path) -> dict[str, str]:
    return {str(path.relative_to(directory)): path.read_text(encoding="utf-8") for path in directory.rglob("*.json")}


@respx.mock
def test_the_script_writes_exactly_the_files_under_recipes(recipes_dir: Path, tmp_path: Path) -> None:
    assert main(["--out", str(tmp_path / "out")]) == 0
    assert _texts(tmp_path / "out") == _texts(recipes_dir)


# The kerg and Stuttgart payloads are too large to commit, so their pins are checked against the live source.
@pytest.mark.live
@pytest.mark.parametrize("shipped", [BUNDESTAGSWAHL_2025, STUTTGART_POPULATION], ids=lambda r: str(r.file))
def test_the_pinned_payload_is_what_the_source_serves(shipped: ShippedRecipe) -> None:
    (source,) = shipped.compliance.sources
    with build_client() as client:
        response = client.get(source.dataset_uri)
    response.raise_for_status()
    assert hashlib.sha256(response.content).hexdigest() == source.sha256
