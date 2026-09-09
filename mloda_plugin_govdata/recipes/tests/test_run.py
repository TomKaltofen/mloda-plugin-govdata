"""A recipe over a captured fixture runs through mloda.run_all in a fresh process."""

import hashlib
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from mloda_plugin_govdata.recipes import load_recipe

FFCSV_FIXTURES = Path(__file__).resolve().parents[2] / "feature_groups" / "destatis" / "tests" / "fixtures" / "ffcsv"
LAND_TABLE_ZIP = FFCSV_FIXTURES / "12411-0010_2024_de_flat.zip"

_SUBPROCESS_SCRIPT = textwrap.dedent(
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


def test_fixture_recipe_pins_the_captured_payload(fixtures_dir: Path) -> None:
    recipe = load_recipe(fixtures_dir / "land_population.json")
    (source,) = recipe.compliance.sources
    assert source.sha256 == hashlib.sha256(LAND_TABLE_ZIP.read_bytes()).hexdigest()
    assert source.credential_env == ["GENESIS_TOKEN"]


def test_recipe_runs_through_mloda_in_a_fresh_process(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GENESIS_TOKEN", "test-token")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _SUBPROCESS_SCRIPT,
            str(fixtures_dir / "land_population.json"),
            str(LAND_TABLE_ZIP),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "OK"
