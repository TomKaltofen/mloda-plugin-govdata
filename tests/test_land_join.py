"""Land-level join of Destatis DLAND with Bundeswahlleiterin results (Nr); key columns line up without
name mapping. ``LandPopulationPerVoter`` is the consumer FeatureGroup mloda's join fires for."""

from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pytest
import respx
from mloda.user import Feature, PluginCollector, mloda

from mloda_plugin_govdata.feature_groups.destatis import DestatisReader, parse_ffcsv_zip
from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE
from mloda_plugin_govdata.feature_groups.govdata import (
    BundeswahlleiterinReader,
    GovDataFeature,
    GovDataLocator,
    Provenance,
)
from mloda_plugin_govdata.feature_groups.land_join import KERG_URL, LAND_LINK, PARTS, VOTERS, LandPopulationPerVoter
from mloda_plugin_govdata.harmonization.land_codes import check_land_names

FEATURE_GROUPS = Path(__file__).resolve().parents[1] / "mloda_plugin_govdata" / "feature_groups"
LAND_TABLE_ZIP = FEATURE_GROUPS / "destatis" / "tests" / "fixtures" / "ffcsv" / "12411-0010_2024_de_flat.zip"
KERG_SAMPLE = FEATURE_GROUPS / "govdata" / "tests" / "fixtures" / "kerg_sample.csv"
LAND_CODES = {f"{n:02d}" for n in range(1, 17)}
TOKEN = "test-token"


def _mock_both_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DestatisReader, "cache_dir", str(tmp_path))
    monkeypatch.setattr(BundeswahlleiterinReader, "cache_dir", str(tmp_path))
    monkeypatch.setenv("GENESIS_TOKEN", TOKEN)
    respx.post(GENESIS_ONLINE.base_url + "data/tablefile").mock(
        return_value=httpx.Response(
            200, content=LAND_TABLE_ZIP.read_bytes(), headers={"content-type": "application/octet-stream"}
        )
    )
    respx.get(KERG_URL).mock(
        return_value=httpx.Response(200, content=KERG_SAMPLE.read_bytes(), headers={"ETag": '"k1"'})
    )


def _run_land_join() -> Any:
    # links= is required despite LandPopulationPerVoter.input_features() already attaching LAND_LINK
    # to its own Feature: input_features() returns a set, so whether the linked Feature or its
    # sibling is added to the engine first is hash-order dependent; when the sibling goes first, its
    # same-class index injection runs before mloda's own link auto-registration takes effect, and the
    # join fails a fraction of the time depending on PYTHONHASHSEED. Confirmed by 100+ direct runs.
    return mloda.run_all(
        [Feature(LandPopulationPerVoter.NAME)],
        compute_frameworks=["PyArrowTable"],
        links={LAND_LINK},
        plugin_collector=PluginCollector.enabled_feature_groups({GovDataFeature, LandPopulationPerVoter}),
    )


def test_land_keys_line_up_without_name_mapping() -> None:
    destatis = parse_ffcsv_zip(LAND_TABLE_ZIP.read_bytes())
    kerg = BundeswahlleiterinReader._parse(
        KERG_SAMPLE, GovDataLocator.from_string(KERG_URL), Provenance(source="url", url=KERG_URL)
    )

    assert destatis.column("1_variable_code").to_pylist() == ["DLAND"] * 16
    assert set(destatis.column("1_variable_attribute_code").to_pylist()) == LAND_CODES
    assert destatis.schema.field("1_variable_attribute_code").type == pa.string()

    parents = kerg.column("gehört zu").to_pylist()
    land_keys = {nr for nr, parent in zip(kerg.column("Nr").to_pylist(), parents) if parent == "99"}
    assert land_keys == LAND_CODES
    assert kerg.schema.field("Nr").type == pa.string()
    # Wahlkreis numbers (and the federal total, Nr 99, in the full file) never collide with a Land code,
    # so an inner join on Nr keeps exactly the 16 Land rows.
    others = set(kerg.column("Nr").to_pylist()) - LAND_CODES
    assert others and LAND_CODES.isdisjoint(others)


def _expected_ratios() -> dict[str, float]:
    """Population per voter per Land, computed independently of ``LandPopulationPerVoter``."""
    destatis = parse_ffcsv_zip(LAND_TABLE_ZIP.read_bytes())
    population = dict(
        zip(destatis.column("1_variable_attribute_code").to_pylist(), destatis.column("value").to_pylist())
    )
    kerg = BundeswahlleiterinReader._parse(
        KERG_SAMPLE, GovDataLocator.from_string(KERG_URL), Provenance(source="url", url=KERG_URL)
    )
    rows = zip(kerg.column("Nr").to_pylist(), kerg.column("gehört zu").to_pylist(), kerg.column(VOTERS).to_pylist())
    voters = {nr: count for nr, parent, count in rows if parent == "99"}
    assert set(population) == set(voters) == LAND_CODES
    return {key: population[key] / voters[key] for key in LAND_CODES}


@respx.mock
def test_land_join_through_mloda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_both_sources(tmp_path, monkeypatch)

    result = _run_land_join()

    table = result[0]
    assert table.num_rows == 16
    assert set(table.schema.names) == {f"{LandPopulationPerVoter.NAME}~{part}" for part in PARTS}
    assert [step.step_kind for step in result.plan].count("join") == 1
    codes = table.column(f"{LandPopulationPerVoter.NAME}~code").to_pylist()
    assert codes == sorted(codes)  # sorted by Land code, not join order
    check_land_names(zip(codes, table.column(f"{LandPopulationPerVoter.NAME}~land").to_pylist()))
    actual = dict(zip(codes, table.column(f"{LandPopulationPerVoter.NAME}~value").to_pylist()))
    assert actual == pytest.approx(_expected_ratios())
