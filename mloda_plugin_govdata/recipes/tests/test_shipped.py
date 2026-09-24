"""Every shipped recipe file is the writer's output of its definition, loads back, and pins a real payload."""

import hashlib
from pathlib import Path

import pytest

from mloda_plugin_govdata.feature_groups.govdata import build_client
from mloda_plugin_govdata.recipes import build_recipe, load_recipe, recipe_to_json
from scripts.write_recipes import BUNDESTAGSWAHL_2025, RECIPES, RECIPES_DIR, STUTTGART_POPULATION, ShippedRecipe, main

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


def _texts(directory: Path) -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in directory.glob("*.json")}


def test_the_script_rewrites_every_file_under_recipes_unchanged(tmp_path: Path) -> None:
    assert main(["--out", str(tmp_path / "out")]) == 0
    assert _texts(tmp_path / "out") == _texts(RECIPES_DIR)


# The kerg and Stuttgart payloads are too large to commit, so their pins are checked against the live source.
@pytest.mark.live
@pytest.mark.parametrize("shipped", [BUNDESTAGSWAHL_2025, STUTTGART_POPULATION], ids=lambda r: str(r.file))
def test_the_pinned_payload_is_what_the_source_serves(shipped: ShippedRecipe) -> None:
    (source,) = shipped.compliance.sources
    with build_client() as client:
        response = client.get(source.dataset_uri)
    response.raise_for_status()
    assert hashlib.sha256(response.content).hexdigest() == source.sha256
