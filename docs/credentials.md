# GENESIS credentials

The Destatis connector talks to two GENESIS installations. Each needs its own free registration; a token from one is not valid on the other.

| Host | `host` name | Base URL | Env vars | Register |
|------|-------------|----------|----------|----------|
| GENESIS-Online (Statistisches Bundesamt) | `genesis` (default) | `https://genesis.destatis.de/genesisWS/rest/2020/` | `GENESIS_TOKEN`, or `GENESIS_USER` and `GENESIS_PASSWORD` | https://genesis.destatis.de/datenbank/online/ |
| Regionalstatistik (Regionaldatenbank Deutschland, IT.NRW) | `regionalstatistik` | `https://www.regionalstatistik.de/genesisws/rest/2020/` | `REGIONALSTATISTIK_TOKEN`, or `REGIONALSTATISTIK_USER` and `REGIONALSTATISTIK_PASSWORD` | https://www.regionalstatistik.de/datenbank/online/ |

Registration is self-service (same-day in our own experience). The token is shown in the web UI under "Webservice-Schnittstelle (API)"; generating a new one invalidates the old one immediately (Anwenderdokumentation Webservice/API v5.1, section 2.1.3).

## Two paths

- **Token** (default): the token travels in the `username` HTTP header with an empty `password`. Enough for table downloads.
- **User plus password**: needed for `job=true` (batch jobs for tables too large to download directly) and `profile/*` calls. Both values travel as HTTP headers.

Credentials never go into the URL or the form body: the server ignores body credentials and silently runs the call as guest (`Username: GAST`), which the client treats as an authentication failure. Redirects are not followed with credentials attached.

## Where credentials come from

The plugin never reads the environment: no reader and no `GenesisClient` does. The caller reads it and passes the credentials in.

1. An mloda run takes them from its `DataAccessCollection`. Passed once to `run_all`, it reaches every Destatis feature, chained ones included:

   ```python
   import os

   from mloda.user import Credential, DataAccessCollection

   collection = DataAccessCollection(credentials={"genesis": Credential(token=os.environ["GENESIS_TOKEN"])})
   mloda.run_all(features, data_access_collection=collection)
   ```

   `DestatisCredentials.from_env(host).to_credential()` builds the entry from the host's env vars above (whitespace stripped, a half-set pair an error).

   An entry counts only when its handle is a host name (`genesis`, `regionalstatistik`) or it carries a `host` key, so another plugin's token is never sent to GENESIS. Keys are `host`, `token`, `user`, `password`. Several entries for one host are refused; keep one. The collection is checked while features resolve, so a misconfigured entry fails the run even when the table is cached. The reader binds the entry at match time: the handle shows in `mloda.explain`, on the plan step (`bound_credential_handle`) and in the plan lock; the value never does. It binds rather than reads at run time because a declared handle must be registered for every run, cached or not, and one handle cannot name both hosts.

   The `genesis_credentials` options key is retired: a feature carrying it, in group or context, chained ones included, is refused at match time. Register the credential in the collection instead, and rotate a token that was passed in `group` (group options are printed with the feature). One run uses one credential per host; there is no per-feature override.
2. `GenesisClient` takes `DestatisCredentials(host="genesis", token=...)` (or `user=..., password=...`) for direct protocol use.

With nothing registered for the host, a selection already in the parameter cache is served without credentials, so an offline rerun, `peek` and `retrieval` on a cached table work. A cache miss raises `MissingCredentialsError`, naming the handle and the registration page, before any request. The reader never runs as guest; `allow_guest=True` on `GenesisClient` (send no credential headers) exists for the fixture capture script only. `DestatisReader.peek(value, collection)` takes the collection for a miss.

Credentials scoped to one host are refused on the other (`WrongHostCredentialsError`).

```python
from mloda_plugin_govdata.feature_groups.destatis import GENESIS_ONLINE, DestatisCredentials, GenesisClient

with GenesisClient(GENESIS_ONLINE, DestatisCredentials.from_env(GENESIS_ONLINE)) as client:
    client.logincheck()  # raises GenesisAuthError if rejected or run as guest
```

## Result too large

A table over the host's download limit raises `GenesisResultTooLarge` (GENESIS status code 98, or the "too large" status text). Ways out:

- Shrink the selection: fewer `regionalkey` entries, classifying keys, or years.
- Split it into several selections, one feature per selection; each is cached under its own parameters.
- Fetch the table by hand through the host's web portal (the registration page above).

`job=true` (the host prepares the table for a later download) needs the user-plus-password path, but this connector does not submit or fetch jobs (deferred, see [destatis-options.md](destatis-options.md#deferred)); a host that queues a job on its own raises `GenesisJobAccepted`.

## Redaction

`repr` and `str` of `DestatisCredentials` and of the `logincheck` reply are redacted, and every `GenesisError` raised by `GenesisClient.call` (and the methods built on it) has the known secrets scrubbed from its text. The `Parameter` block that GENESIS echoes in each JSON reply loses `username` and `password` at parse time. Errors raised below that layer (transport errors, a `ValueError` from your own code) are not scrubbed, except that mloda masks collection tokens and passwords of 8 or more characters in every error and log of the run. The fixture capture script (`scripts/capture_genesis_fixtures.py`) redacts secret values in any case or URL-encoding before writing and refuses to keep a file in which a secret survived.

## Live tests

Tests marked `genesis_live` are deselected by default and skip with a visible reason when no credentials are set. Run them per host with the env vars above (the tests read them and pass them in):

```bash
GENESIS_TOKEN=... pytest -m "live and genesis_live"
```

## Notebooks

Tutorials 3 to 5 read `GENESIS_TOKEN` (or the user plus password pair) with `from_env`, pass a `DataAccessCollection` to every run, and stop, naming the reason, when none is set.
