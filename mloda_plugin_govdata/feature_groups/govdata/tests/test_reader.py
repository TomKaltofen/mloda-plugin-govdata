"""Level 2 (recorded) and Level 3 (live) tests for the GovData reader."""

import json
from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from mloda.user import Feature, mloda
from mloda_plugins.compute_framework.base_implementations.pyarrow.table import PyArrowTable

from mloda_plugin_govdata.feature_groups.govdata.reader import GovDataFeature, GovDataReader

SLUG = "einwohner-nach-altersgruppen-und-stadtbezirken"
PACKAGE_SHOW = "https://ckan.govdata.de/api/3/action/package_show"


def test_feature_group_metadata() -> None:
    assert GovDataFeature.compute_framework_rule() == {PyArrowTable}
    assert isinstance(GovDataFeature.input_data(), GovDataReader)


@respx.mock
def test_load_data_level2(fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GovDataReader, "cache_dir", str(tmp_path))
    package_show = (fixtures_dir / "package_show.json").read_text(encoding="utf-8")
    csv_bytes = (fixtures_dir / "population_sample.csv").read_bytes()
    distribution_url = json.loads(package_show)["result"]["resources"][0]["url"]

    respx.get(PACKAGE_SHOW).mock(return_value=httpx.Response(200, text=package_show))
    respx.get(distribution_url).mock(return_value=httpx.Response(200, content=csv_bytes, headers={"ETag": '"v1"'}))

    result = mloda.run_all(
        [
            Feature("Einwohner", options={GovDataReader.__name__: SLUG}),
            Feature("Stadtbezirk", options={GovDataReader.__name__: SLUG}),
        ],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert set(table.schema.names) == {"Einwohner", "Stadtbezirk"}
    assert table.num_rows == 1000
    assert table.schema.field("Einwohner").type == pa.int64()


@pytest.mark.live
def test_live_end_to_end() -> None:
    result = mloda.run_all(
        [Feature("Einwohner", options={GovDataReader.__name__: SLUG})],
        compute_frameworks=["PyArrowTable"],
    )
    table = result[0]
    assert table.num_rows > 20_000
    assert table.schema.field("Einwohner").type == pa.int64()
