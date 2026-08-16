# GENESIS credentials

The Destatis connector talks to two GENESIS installations. Each needs its own free registration; a token from one is not valid on the other.

| Host | `host` name | Base URL | Env vars | Register |
|------|-------------|----------|----------|----------|
| GENESIS-Online (Statistisches Bundesamt) | `genesis` (default) | `https://genesis.destatis.de/genesisWS/rest/2020/` | `GENESIS_TOKEN`, or `GENESIS_USER` and `GENESIS_PASSWORD` | https://genesis.destatis.de/datenbank/online/ |
| Regionalstatistik (Regionaldatenbank Deutschland, IT.NRW) | `regionalstatistik` | `https://www.regionalstatistik.de/genesisws/rest/2020/` | `REGIONALSTATISTIK_TOKEN`, or `REGIONALSTATISTIK_USER` and `REGIONALSTATISTIK_PASSWORD` | https://www.regionalstatistik.de/datenbank/online/ |

Registration is self-service and same-day: the token appears in the web UI right after signup ("Webservice-Schnittstelle (API)"). A new token invalidates the old one immediately.

## Two paths

- **Token** (default): the token travels in the `username` HTTP header with an empty `password`. Enough for table downloads.
- **User plus password**: needed for `job=true` (batch jobs for tables too large to download directly) and `profile/*` calls. Both values travel as HTTP headers.

Credentials never go into the URL or the form body: the server ignores body credentials and silently runs the call as guest (`Username: GAST`), which the client treats as an authentication failure. Redirects are not followed with credentials attached.

## Resolution order

1. Explicit: `DestatisCredentials(host="genesis", token=...)` (or `user=..., password=...`) passed to `GenesisClient`, or in mloda `Options(context={"genesis_credentials": ...})`. Context only; the key is refused in `group`, which is hashed and printed with the feature.
2. Env vars of the host, chosen by the host prefix. Whitespace is stripped.
3. Otherwise `MissingCredentialsError` names the env vars and the registration page for that host. Nothing is sent.

Credentials scoped to one host are refused on the other (`WrongHostCredentialsError`), and env resolution never falls back across hosts.

```python
from mloda_plugin_govdata.feature_groups.destatis import GenesisClient

with GenesisClient("genesis") as client:  # credentials from GENESIS_TOKEN
    client.logincheck()  # raises GenesisAuthError if rejected or run as guest
```

## Redaction

`repr` and `str` of credentials, of the `logincheck` reply, and of every raised error are redacted. The `Parameter` block that GENESIS echoes in each JSON reply loses `username` and `password` at parse time. The fixture capture script (`scripts/capture_genesis_fixtures.py`) redacts secret values in any case or URL-encoding before writing.

## Live tests

Tests marked `genesis_live` are deselected by default and skip with a visible reason when no credentials are set. Run them per host with the env vars above:

```bash
GENESIS_TOKEN=... pytest -m "live and genesis_live"
```
