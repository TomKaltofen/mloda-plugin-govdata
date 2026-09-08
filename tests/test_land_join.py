"""Land-level join of a Destatis table (DLAND) with Bundeswahlleiterin results (Nr).

The key columns line up on real data without any name mapping. The mloda join itself is a
strict xfail: mloda 0.10's ``Engine._add_index_feature_from_links`` injects both link key
columns into every feature set of a same-class link, ignoring the discriminators, so each reader
is asked for the other side's key and whichever loads first fails. A companion test pins that
exact error, so the xfail cannot hide a different regression.
"""

from pathlib import Path
from typing import Any, ClassVar

import httpx
import pyarrow as pa
import pytest
import respx
from mloda.provider import FeatureGroup, FeatureSet
from mloda.user import Feature, FeatureName, JoinSpec, Link, Options, PluginCollector, mloda

from mloda_plugin_govdata.feature_groups.destatis import DestatisReader, parse_ffcsv_zip
from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE
from mloda_plugin_govdata.feature_groups.govdata import (
    BundeswahlleiterinReader,
    GovDataFeature,
    GovDataLocator,
    Provenance,
)

FEATURE_GROUPS = Path(__file__).resolve().parents[1] / "mloda_plugin_govdata" / "feature_groups"
LAND_TABLE_ZIP = FEATURE_GROUPS / "destatis" / "tests" / "fixtures" / "ffcsv" / "12411-0010_2024_de_flat.zip"
KERG_SAMPLE = FEATURE_GROUPS / "govdata" / "tests" / "fixtures" / "kerg_sample.csv"
KERG_URL = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv"
LAND_LOCATOR = {"name": "12411-0010", "startyear": 2024, "endyear": 2024}
LAND_CODES = {f"{n:02d}" for n in range(1, 17)}
TOKEN = "test-token"
VOTERS = "Wahlberechtigte Erststimmen Endgültig"
OTHER_SIDES_KEY = r"Unknown feature\(s\) '(Nr|1_variable_attribute_code)'"

# The checklist's link shape: both sides resolve to GovDataFeature, so the reader option is the discriminator.
LAND_LINK = Link.inner(
    JoinSpec(GovDataFeature, "1_variable_attribute_code"),
    JoinSpec(GovDataFeature, "Nr"),
    left_discriminator={DestatisReader.__name__: LAND_LOCATOR},
    right_discriminator={BundeswahlleiterinReader.__name__: KERG_URL},
)


class LandVoters(FeatureGroup):
    """Test-only consumer needing one column per side; mloda executes a link only for such a consumer."""

    NAME: ClassVar[str] = "land_population_per_voter"
    seen_columns: ClassVar[list[str]] = []

    @classmethod
    def feature_names_supported(cls) -> set[str]:
        return {cls.NAME}

    def input_features(self, options: Options, feature_name: FeatureName) -> set[Feature] | None:
        return {
            Feature("value", options={DestatisReader.__name__: LAND_LOCATOR}, link=LAND_LINK),
            Feature(VOTERS, options={BundeswahlleiterinReader.__name__: KERG_URL}),
        }

    @classmethod
    def calculate_feature(cls, data: Any, features: FeatureSet) -> Any:
        cls.seen_columns[:] = list(data.schema.names)
        pairs = zip(data.column("value").to_pylist(), data.column(VOTERS).to_pylist())
        ratio = pa.array([population / voters for population, voters in pairs], type=pa.float64())
        return data.append_column(cls.NAME, ratio)


def _mock_both_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(DestatisReader, "cache_dir", str(tmp_path))
    monkeypatch.setattr(BundeswahlleiterinReader, "cache_dir", str(tmp_path))
    monkeypatch.setenv("GENESIS_TOKEN", TOKEN)
    LandVoters.seen_columns.clear()
    respx.post(GENESIS_ONLINE.base_url + "data/tablefile").mock(
        return_value=httpx.Response(
            200, content=LAND_TABLE_ZIP.read_bytes(), headers={"content-type": "application/octet-stream"}
        )
    )
    respx.get(KERG_URL).mock(
        return_value=httpx.Response(200, content=KERG_SAMPLE.read_bytes(), headers={"ETag": '"k1"'})
    )


def _run_land_join() -> Any:
    return mloda.run_all(
        [Feature(LandVoters.NAME)],
        compute_frameworks=["PyArrowTable"],
        links={LAND_LINK},
        plugin_collector=PluginCollector.enabled_feature_groups({GovDataFeature, LandVoters}),
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


@respx.mock
def test_land_join_today_asks_each_reader_for_the_other_sides_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_both_sources(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match=OTHER_SIDES_KEY):
        _run_land_join()


@pytest.mark.xfail(
    strict=True,
    raises=ValueError,
    reason="mloda 0.10: same-class link keys are injected into both sides, so each reader is asked for the other's key",
)
@respx.mock
def test_land_join_through_mloda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_both_sources(tmp_path, monkeypatch)

    result = _run_land_join()

    table = result[0]
    assert table.num_rows == 16
    assert set(LandVoters.seen_columns) >= {"1_variable_attribute_code", "value", "Nr", VOTERS}
    assert [step.step_kind for step in result.plan].count("join") == 1
