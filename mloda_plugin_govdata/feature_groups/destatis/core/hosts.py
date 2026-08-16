"""GENESIS webservice hosts: base URL, env-var prefix for credentials, registration page."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenesisHost:
    """One GENESIS installation. Registrations (and tokens) are per host, never shared."""

    name: str  # short name used in options and error messages, e.g. "genesis"
    base_url: str  # ".../rest/2020/", trailing slash included
    env_prefix: str  # GENESIS -> GENESIS_TOKEN, GENESIS_USER, GENESIS_PASSWORD
    registration_url: str  # start page with the free registration link
    label: str  # human-readable name for messages

    def __post_init__(self) -> None:
        if not self.base_url.endswith("/"):
            object.__setattr__(self, "base_url", self.base_url + "/")
        if not self.env_prefix.isidentifier() or self.env_prefix != self.env_prefix.upper():
            raise ValueError(f"env_prefix must be an upper-case identifier, got {self.env_prefix!r}")

    def env_var(self, suffix: str) -> str:
        return f"{self.env_prefix}_{suffix}"

    def url(self, path: str) -> str:
        return self.base_url + path.lstrip("/")


# genesis.destatis.de is the current host; www-genesis.destatis.de answers with a 307 redirect.
GENESIS_ONLINE = GenesisHost(
    name="genesis",
    base_url="https://genesis.destatis.de/genesisWS/rest/2020/",
    env_prefix="GENESIS",
    registration_url="https://genesis.destatis.de/datenbank/online/",
    label="GENESIS-Online (Statistisches Bundesamt)",
)

# Lower-case "genesisws" per that host's OpenAPI ``servers`` entry; own registration, run by IT.NRW.
REGIONALSTATISTIK = GenesisHost(
    name="regionalstatistik",
    base_url="https://www.regionalstatistik.de/genesisws/rest/2020/",
    env_prefix="REGIONALSTATISTIK",
    registration_url="https://www.regionalstatistik.de/datenbank/online/",
    label="Regionalstatistik (Regionaldatenbank Deutschland)",
)

KNOWN_HOSTS: dict[str, GenesisHost] = {host.name: host for host in (GENESIS_ONLINE, REGIONALSTATISTIK)}


def resolve_host(host: GenesisHost | str) -> GenesisHost:
    """A known host name or an explicit ``GenesisHost`` (unknown hosts need base URL and prefix)."""
    if isinstance(host, GenesisHost):
        return host
    try:
        return KNOWN_HOSTS[host]
    except KeyError:
        raise ValueError(
            f"Unknown GENESIS host {host!r}; known: {', '.join(sorted(KNOWN_HOSTS))}. "
            "Pass a GenesisHost with base_url and env_prefix for another installation."
        ) from None
