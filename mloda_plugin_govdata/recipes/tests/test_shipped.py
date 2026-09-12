"""Every shipped recipe file is the writer's output of its definition and loads back."""

from pathlib import Path

import pytest

from mloda_plugin_govdata.recipes import build_recipe, load_recipe, recipe_to_json

from .conftest import RECIPES_DIR
from .shipped import RECIPES, ShippedRecipe

# The first recipe file predates the definitions module; its pin lives in test_writer.py.
LEGACY = {"land_population.json"}


@pytest.fixture(autouse=True)
def _no_genesis_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GENESIS_TOKEN", "GENESIS_USER", "GENESIS_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("shipped", RECIPES, ids=[r.file for r in RECIPES])
def test_the_file_is_what_the_writer_produces(recipes_dir: Path, shipped: ShippedRecipe) -> None:
    expected = recipe_to_json(build_recipe(shipped.features, shipped.compliance, shipped.links))
    assert (recipes_dir / shipped.file).read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("shipped", RECIPES, ids=[r.file for r in RECIPES])
def test_the_file_loads_with_its_compliance_complete(recipes_dir: Path, shipped: ShippedRecipe) -> None:
    loaded = load_recipe(recipes_dir / shipped.file)
    assert len(loaded.features) == len(shipped.features)
    assert len(loaded.links) == len(shipped.links)
    for source in loaded.compliance.sources:
        assert source.modifications, "dl-de/by-2-0 wants the changes marked"
        assert source.retrieved_at.tzinfo is not None


def test_every_file_under_recipes_is_pinned() -> None:
    assert {path.name for path in RECIPES_DIR.glob("*.json")} == {r.file for r in RECIPES} | LEGACY
