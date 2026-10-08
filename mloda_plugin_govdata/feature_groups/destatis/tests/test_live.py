"""Live smoke against the GENESIS hosts (deselected by default; needs credentials per host)."""

from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from mloda.user import Feature, mloda

from mloda_plugin_govdata.feature_groups.destatis.core.api import GenesisClient
from mloda_plugin_govdata.feature_groups.destatis.core.auth import DestatisCredentials
from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE, KNOWN_HOSTS
from mloda_plugin_govdata.feature_groups.destatis.reader import DestatisReader

# Bevoelkerung by Kreis and by Land, Stichtag: small enough for a direct download, GENESIS-Online only.
LIVE_LOCATORS = [
    {"name": "12411-0015", "regionalvariable": "KREISE", "regionalkey": ["03159"], "startyear": 2016, "endyear": 2016},
    {"name": "12411-0010", "startyear": 2024, "endyear": 2024},
]


@pytest.mark.live
@pytest.mark.genesis_live
@pytest.mark.parametrize("host_name", sorted(KNOWN_HOSTS))
def test_whoami_and_logincheck(host_name: str) -> None:
    host = KNOWN_HOSTS[host_name]
    if DestatisCredentials.from_env(host) is None:
        pytest.skip(f"no credentials for {host.label}: set {host.env_var('TOKEN')} or user plus password")
    with GenesisClient(host) as client:
        assert client.whoami().user_agent.startswith("mloda-plugin-govdata/")
        reply = client.logincheck()
    assert reply.is_success and not reply.is_guest


@pytest.mark.live
@pytest.mark.genesis_live
@pytest.mark.parametrize("locator", LIVE_LOCATORS, ids=lambda locator: locator["name"])
def test_tablefile_end_to_end(locator: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real GENESIS table arrives as a typed Arrow table via mloda.run_all from a clean cache."""
    if DestatisCredentials.from_env(GENESIS_ONLINE) is None:
        pytest.skip(f"no credentials for {GENESIS_ONLINE.label}: set {GENESIS_ONLINE.env_var('TOKEN')}")
    monkeypatch.setattr(DestatisReader, "cache_dir", str(tmp_path))
    result = mloda.run_all(
        [Feature("value", options={DestatisReader.__name__: locator})], compute_frameworks=["PyArrowTable"]
    )
    table = result[0]
    assert table.num_rows > 0
    assert table.schema.field("value").type == pa.float64()
