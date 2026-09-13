"""Every shipped recipe file is the writer's output of its definition, loads back, and pins a real payload."""

import hashlib
from pathlib import Path

import pytest

from mloda_plugin_govdata.feature_groups.govdata import build_client
from mloda_plugin_govdata.recipes import build_recipe, load_recipe, recipe_to_json

from .conftest import RECIPES_DIR
from .shipped import BUNDESTAGSWAHL_2025, RECIPES, STUTTGART_POPULATION, ShippedRecipe

# The first recipe file predates the definitions module; its pin lives in test_writer.py.
LEGACY = {"land_population.json"}
IDS = [r.file for r in RECIPES]


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


def test_every_file_under_recipes_is_pinned() -> None:
    assert {path.name for path in RECIPES_DIR.glob("*.json")} == {r.file for r in RECIPES} | LEGACY


# The kerg and Stuttgart payloads are too large to commit, so their pins are checked against the live source.
@pytest.mark.live
@pytest.mark.parametrize("shipped", [BUNDESTAGSWAHL_2025, STUTTGART_POPULATION], ids=lambda r: str(r.file))
def test_the_pinned_payload_is_what_the_source_serves(shipped: ShippedRecipe) -> None:
    (source,) = shipped.compliance.sources
    with build_client() as client:
        response = client.get(source.dataset_uri)
    response.raise_for_status()
    assert hashlib.sha256(response.content).hexdigest() == source.sha256
