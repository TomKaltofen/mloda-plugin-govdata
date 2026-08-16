"""Live smoke against the GENESIS hosts (deselected by default; needs credentials per host)."""

import pytest

from mloda_plugin_govdata.feature_groups.destatis.core.api import GenesisClient
from mloda_plugin_govdata.feature_groups.destatis.core.auth import DestatisCredentials
from mloda_plugin_govdata.feature_groups.destatis.core.hosts import KNOWN_HOSTS


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
