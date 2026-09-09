"""Recipes over captured fixtures in a fresh process: the loader registers the feature groups and mloda runs them."""

import hashlib
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from mloda_plugin_govdata.recipes import load_recipe

REPO_ROOT = Path(__file__).resolve().parents[3]
FFCSV_FIXTURES = REPO_ROOT / "mloda_plugin_govdata" / "feature_groups" / "destatis" / "tests" / "fixtures" / "ffcsv"
LAND_TABLE_ZIP = FFCSV_FIXTURES / "12411-0010_2024_de_flat.zip"

_RUN_SCRIPT = textwrap.dedent(
    """
    import sys
    import httpx
    import respx
    from mloda.user import mloda

    # The only plugin import before loading: the loader must register the feature groups itself.
    from mloda_plugin_govdata.recipes import load_recipe

    recipe_path, fixture_zip, cache_dir = sys.argv[1:4]
    recipe = load_recipe(recipe_path)

    from mloda_plugin_govdata.feature_groups.destatis import DestatisReader
    from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE

    DestatisReader.cache_dir = cache_dir
    with open(fixture_zip, "rb") as handle:
        zip_bytes = handle.read()
    with respx.mock:
        respx.post(GENESIS_ONLINE.base_url + "data/tablefile").mock(
            return_value=httpx.Response(200, content=zip_bytes, headers={"content-type": "application/octet-stream"})
        )
        result = mloda.run_all(recipe.features, compute_frameworks=["PyArrowTable"], links=set(recipe.links))
    table = result[0]
    assert table.num_rows == 16, table.num_rows
    assert sorted(table.column_names) == ["1_variable_attribute_code", "value"], table.column_names
    assert sorted(table.column("1_variable_attribute_code").to_pylist()) == [f"{n:02d}" for n in range(1, 17)]
    print("OK")
    """
)

_LINK_SCRIPT = textwrap.dedent(
    """
    import sys
    from mloda_plugin_govdata.recipes import load_recipe

    recipe = load_recipe(sys.argv[1])

    from mloda.user import Feature
    from mloda_plugin_govdata.feature_groups.govdata import GovDataFeature

    (link,) = recipe.links
    assert link.left_feature_group is GovDataFeature and link.right_feature_group is GovDataFeature, link
    assert link.left_index.index == ("1_variable_attribute_code",) and link.right_index.index == ("Nr",), link
    # The discriminators must equal the features' option values exactly, or mloda never matches the node.
    options = [feature.options.group for feature in recipe.features if isinstance(feature, Feature)]
    assert link.left_discriminator in options and link.right_discriminator in options, (link, options)
    print("OK")
    """
)


@pytest.fixture(autouse=True)
def _no_genesis_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GENESIS_TOKEN", "GENESIS_USER", "GENESIS_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


def _fresh_process(script: str, *args: str) -> None:
    completed = subprocess.run([sys.executable, "-c", script, *args], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "OK"


def test_fixture_recipe_pins_the_captured_payload(fixtures_dir: Path) -> None:
    recipe = load_recipe(fixtures_dir / "land_population.json")
    (source,) = recipe.compliance.sources
    assert source.sha256 == hashlib.sha256(LAND_TABLE_ZIP.read_bytes()).hexdigest()
    assert source.credential_env == ["GENESIS_TOKEN"]


def test_the_repo_root_recipe_is_the_fixture(fixtures_dir: Path) -> None:
    shipped = REPO_ROOT / "recipes" / "land_population.json"
    assert shipped.read_text("utf-8") == (fixtures_dir / "land_population.json").read_text("utf-8")


def test_recipe_runs_through_mloda_in_a_fresh_process(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GENESIS_TOKEN", "test-token")
    _fresh_process(_RUN_SCRIPT, str(fixtures_dir / "land_population.json"), str(LAND_TABLE_ZIP), str(tmp_path))


def test_links_resolve_in_a_fresh_process(fixtures_dir: Path) -> None:
    _fresh_process(_LINK_SCRIPT, str(fixtures_dir / "land_join.json"))
