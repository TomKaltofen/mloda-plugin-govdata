# AP2 implementation plan: Destatis connector and harmonization

Status: draft v2, 2026-08-16. Living document until M2 (30 Sep 2026): update it
when a checkpoint or cut line moves. Budget, funder-update dates, capacity
scenarios, risks, and the ADR drafts live in the private planning companion
repo (`planning/ap2-execution-notes.md` there); this file carries scope,
architecture, rules, and schedule. The tickable build order (one slice per
PR, checkpoints, cut lines) is [ap2-build-checklist.md](ap2-build-checklist.md).

## 1. Contract and acceptance

From the funding application (Vorhabenbeschreibung, AP2 row), the scope is:

> GENESIS-API-Anbindung mit Authentifizierung. AGS-NUTS-Mapper,
> Zeitreihen-Alignment. 3 weitere reproduzierbare Rezepte.

and the milestone is:

> M2 (30.09.): Destatis-Connector funktionsfähig, Harmonisierung
> implementiert, 6 Rezepte gesamt.

Definition of done, checkable:

1. A `DestatisReader` pulls at least two real GENESIS tables end to end (auth,
   request, download, parse) into typed Arrow tables via the same
   `mloda.run_all` call shape as the M1 readers.
2. The harmonization module maps 5-digit AGS (Kreis) keys to NUTS-1/2/3 with
   explicit edition selection, and re-bases at least one real multi-year Kreis
   series across a Gebietsstand change using the BBSR Umsteigeschluessel.
3. A documented, typed period representation joins Destatis annual data with
   one M1 source at Land level (see decision D2).
4. Six recipe files exist (three new, three M1 retrofits), each carrying
   license id, attribution string, dataset URI, retrieval timestamp, payload
   sha256, and modification markers.
5. `tox` green (pytest, ruff, mypy strict, bandit), no live network in the
   default test run, README and demo notebook updated.

## 2. Starting position

Settled by M1 and the research phase (details and sources in the planning
repo):

- GENESIS account and token exist; a live `whoami` has not been run yet. That
  is the first task.
- Every request except `helloworld/whoami` needs auth. `job=true` and
  `profile/*` calls need username plus password; the token is not accepted
  there. Dual-path credentials are a verified constraint.
- POST-only API since 15 Jul 2025 (SOAP and REST GET are gone). Third-party
  examples predate this; the Anwenderdokumentation v5.0 (06.05.2025) is the
  contract. `pyproject.toml` still says "GENESIS API v3"; fix in WP-G.
- Documented limits: a cap on parallel requests (value not fixed), server-side
  termination of requests over 15 minutes, `pagelength` max 25000. No
  per-day quota is documented.
- `data/tablefile` formats: csv, datencsv (default), ffcsv, xlsx, genml, html;
  CSV variants arrive zipped. ffcsv has fixed English headers and is the tidy
  choice. Quirks remain: windows-1252, semicolons, decimal commas, value
  markers. The M1 encoding ladder and marker sets apply (`core/parse.py`:
  `-` is zero, `. ... / x ()` are null-like).
- Licensing is clean: GENESIS dl-de/by-2-0; Eurostat correspondence and LAU
  tables CC-BY-4.0; GV-ISys reproduction with attribution; BBSR confirmed in
  writing that the Umsteigeschluessel are dl-de/by-2-0 and may be bundled and
  redistributed with visible attribution to "Laufende Raumbeobachtung des
  BBSR" (long form in the planning repo).
- AGS-to-NUTS mapping is net-new: no maintained Python library does it (2026
  survey). Reference inputs are Excel and GV100 fixed-width ASCII.
- M1 chassis, and what it does and does not give AP2:
  - `core/client.py`: httpx client with four-part timeout, polite User-Agent,
    tenacity retry with jitter; Retry-After is honored in seconds form only.
  - `core/cache.py`: `DownloadCache` is GET-only, keyed by URL, conditional
    revalidation. It has no POST, parameter, or refresh support; the POST
    cache in WP-B is a sibling, not an extension.
  - `reader.py`: `BaseGovDataReader._read_table` hardcodes CKAN resolution
    plus a GET download; `_parse` receives a `ResolvedDistribution`. A POST
    reader needs a fetch seam first (WP-B, first item).
  - Tests: three-level posture by convention (fixture, recorded, live), live
    gated by the pytest marker `live` (`addopts = -m 'not live'`), no env
    gating today. `respx` and `hypothesis` are already dev dependencies.
  - `docs/adding-a-reader.md`, `peek`, `search_datasets` (lazy pagination),
    the UBA `_check_layout` drift guard, and the demo notebook
    `demos/govdata_demo.py`.

## 3. Users, in one line each

Full personas and the interview plan are in the planning repo
(`planning/research/user-research-mom-test-first-run.md`). What each must
never hit:

- U1 data journalist: silent zero-vs-missing confusion, or a region silently
  dropped because its AGS changed.
- U2 empirical researcher: an unlabeled re-based value, or a crosswalk applied
  in the wrong direction.
- U3 civic-tech Python user (often on pystatis): raw-access rebuilds; our layer
  is harmonization, typed output, one interface across portals.
- U4 contributor: needing a GENESIS account to run the fixture tests, or more
  than an hour to add a table recipe by following the docs.
- U5 CI and unattended runs: any credential or network need in the default
  test run; fork PRs must pass.

## 4. Decisions made in this plan (v2)

Recorded here so the work packages can be short. Each becomes an ADR in the
planning repo (`decisions/`) at the first implementation PR.

- **D1 Feature surface.** Reader level: feature names are the ffcsv column
  names (`value`, `time`, `1_variable_attribute_code`, ...), long format, one
  locator per table selection. Measure and region selection happen in the
  locator, not in feature names. Harmonized, application-style names
  (`destatis__bevoelkerung__kreise`) are derived FeatureGroups in WP-E; ASCII
  rule: ä/ö/ü/ß become ae/oe/ue/ss.
- **D2 Cross-portal join level.** M1 sources carry no AGS: `kerg.csv` keys on
  Wahlkreis number (`Nr;Gebiet;gehört zu`), UBA keys on `station_id`. The AP2
  cross-portal recipe joins Destatis population with Bundestagswahl results at
  Land level (kerg rows with `gehört zu = 99`) through a 16-row Land-to-AGS-2
  constant. Kreis-level cross-portal joins and UBA station-to-region mapping
  are out of scope for AP2.
- **D3 Job path.** M2 scope is detection of the "result too large" envelope
  plus an actionable error (why the password path is needed, how to shrink
  the selection, how to fetch manually). The full submit/poll/download/remove
  path is stretch. Recipes are chosen small enough not to need it.
- **D4 Mapping level.** Kreis (5-digit AGS) is M2 scope. Gemeinde (8-digit)
  and 12-digit ARS are stretch; the data model keeps keys as strings so the
  levels can be added without migration.
- **D5 Hosts and discovery.** The base URL is a field on the locator with
  GENESIS-Online as default. Regionalstatistik and the Zensus database are not
  implemented and not designed beyond that field. No catalogue/discovery
  helper in AP2; recipes name table codes.
- **D6 POST cache freshness.** Cache hit wins (deterministic reruns), explicit
  `refresh` escape hatch, no TTL refetch. A warning is logged when a cached
  payload is older than 30 days. Recipes carry retrieval timestamp and sha256
  so staleness is visible.
- **D7 Politeness.** The Destatis client serializes GENESIS calls behind a
  process-level lock, so mloda's threading or multiprocessing modes cannot
  fan out requests. No client-side parallelism, ever.
- **D8 Live tests.** Marker `live` stays; live tests additionally skip with a
  visible reason when `GENESIS_TOKEN` (or user plus password) is absent. Run
  manually before each biweekly funder update, never scheduled: the
  application mentions a weekly live CI run, and the reconciliation (ToS
  question open, manual smoke instead) is written for the funder in the
  planning repo.
- **D9 Fixture attribution.** Real payloads committed as fixtures ship with a
  `NOTICE` in the fixture directory naming source, license, and attribution
  string (Destatis, Eurostat, BBSR long form).
- **D10 Validation.** Pydantic models for the error envelope, the locator, and
  the recipe file (fail-fast, as the application names it); table columns are
  typed through the Arrow schema and layout drift raises.
- **D11 Excel reader.** openpyxl (pandas is already a dependency and
  `read_excel` needs it anyway); recorded with the 7-day exclude-newer window
  in mind.

## 5. Work packages

Estimates are effort, not calendar. Sum: about 245 h. Budget and pace
scenarios are in the planning companion.

### WP-A: GENESIS client and auth (about 45 h)

`feature_groups/destatis/core/` next to the govdata core, reusing
`client.py`.

- Endpoints in scope (verify names and parameters against doc v5.0 in
  week 1): `helloworld/whoami`, `helloworld/logincheck`, `data/tablefile`
  (parameters: `name`, `startyear`, `endyear`, `regionalvariable`,
  `regionalkey`, `classifyingvariable1..3`, `classifyingkey1..3`, `format`,
  `language`, `job`, `compress`, `transpose`, `stand`), and for the stretch
  job path `catalogue/jobs`, `data/resultfile`, `profile/removeresult`.
- `DestatisCredentials`: explicit option, then env (`GENESIS_TOKEN`,
  `GENESIS_USER`, `GENESIS_PASSWORD`; host-prefixed variants). Whitespace
  normalized. Never logged, never in cache keys, metadata, recipes, snapshots,
  or fixtures.
- POST request layer: form-encoded, auth mechanism verified against the doc
  (do not trust token-as-username folklore), `language` pinned per request,
  the D7 lock.
- Error envelope: application status inside HTTP 200 bodies, characterized
  in week 1 (bad credentials, unknown table, empty selection, too large, job
  accepted), mapped to typed exceptions. Missing credentials error names the
  env vars and says registration is free and same-day, with the URL. Auth
  failures are not retried.

### WP-B: Table retrieval, ffcsv parsing, reader (about 50 h)

- Fetch seam in `BaseGovDataReader`: extract `_fetch(locator, client) ->
  cached path` from `_read_table` so M1 readers keep CKAN plus GET and
  `DestatisReader` overrides with POST plus the parameter cache. `_parse`
  gets a source-neutral provenance object instead of `ResolvedDistribution`.
- Parameter-keyed POST cache: key over host, endpoint, canonically ordered
  and normalized parameters (sorted region lists, integer years), credentials
  excluded; D6 freshness rules; shares the cache directory with the GET path
  without collisions.
- `data/tablefile` with `format=ffcsv`, zip unpacking (characterize member
  count and names), decompressed-size cap.
- ffcsv parser in `destatis/core/parse.py`: import the encoding ladder,
  dialect, decimal-comma and marker handling from `govdata/core/parse.py`;
  add the English header contract, time column parsing (delegated to the
  WP-E period model), quality-flag columns if present. A column that cannot be
  typed raises with the offending cell.
- `DestatisLocator`: table code (`12411-0015` style), optional region and
  classifying selection, start/end year, host, language, format pin;
  `from_string` accepts a bare table code.
- `DestatisReader(BaseGovDataReader)` with `_fetch`, `_parse`, `suffix`, and
  `peek`.

### WP-C: Large-table detection (about 8 h)

D3: detect the too-large envelope and raise the actionable error. Full job
path is stretch (about 20 h if pulled in).

### WP-D: AGS-to-NUTS mapper (about 45 h)

Standalone pure-Python module `mloda_plugin_govdata/harmonization/`, usable
without mloda, wrapped by FeatureGroups in WP-E.

- Loaders: Eurostat NUTS correspondence and LAU-to-NUTS (xlsx), Destatis
  GV-ISys (xlsx and GV100 fixed-width), BBSR Umsteigeschluessel (xlsx,
  Kreise; Gemeinden with D4 stretch). Runtime fetch through the GET cache,
  pinned by URL plus sha256; a small redistributable extract per source ships
  as a fixture (D9).
- Mapping core: 5-digit AGS to NUTS-1/2/3 for a named edition pair. Keys are
  strings with leading zeros everywhere.
- Edition model: every call names Gebietsstand and NUTS version; default
  "latest shipped" with a warning when data year and edition year diverge.
  Current Eurostat tables are NUTS 2027 / LAU 2025; that is data, not a
  constant.
- Diagnostics as data: matched rows plus a structured unmatched-key report;
  fail-loud default, opt-in drop or flagged pass-through.

### WP-E: Period model, re-basing, mloda integration (about 40 h)

- Period model: typed representation (period start date plus frequency tag)
  with parsers for GENESIS time labels (years first; quarters and months as
  found in the chosen tables) and for the M1 time columns. Join at equal
  frequency only; mismatch raises with resampling guidance.
- Re-basing: BBSR proportional keys onto a target Gebietsstand; explicit
  direction and key edition, documented rounding, share-sum check with
  tolerance (renormalize inside, raise beyond). Every re-based value carries a
  flag column; census breaks (2011, 2022) are noted, not smoothed.
- mloda integration: harmonization and alignment as derived FeatureGroups over
  the reader outputs (`input_features` composition). Read mloda-registry
  guides 02, 03, 04, 08, 11, 26, 27 first; the D1 naming scheme is applied
  here.

### WP-F: Recipes, six total (about 35 h)

- Recipe format first: mloda's JSON `feature_config` (`load_features_from_config`
  exists in mloda 0.10) plus a small Feature-to-JSON writer and a compliance
  block (D10 model): license id, attribution string, dataset URI, retrieval
  timestamp, payload sha256, modification markers, required credential env
  names. No credentials in recipes.
- Three new recipes (tables to be pinned in week 0/1; all sized to skip the
  job path): (1) population by Kreis over time, GENESIS 12411 family, the U2
  re-basing scenario; (2) a Kreis-level labor-market or income indicator, the
  U1 rate-with-denominator scenario; (3) Destatis population by Land joined
  with Bundestagswahl results by Land (D2), the U3 and Demo Day scenario.
- Three M1 retrofits (population, elections, UBA) authored and tested as
  recipe files. Not free: budgeted here.

### WP-G: Docs, demo, handoff (about 20 h, woven through)

README Destatis section, `docs/adding-a-reader.md` extension for the
Destatis path, credential setup doc, demo notebook chapter, `pyproject.toml`
description fix (v3 to v5.0), planning-repo updates (milestone status, ADRs
0002 onward, learnings as they happen). One GitHub issue per WP plus an M2
milestone on the upstream repo, so U4 and the cut lines are visible.

## 6. Rulebook (edge cases the tests are graded against)

Each item is handled, detected-and-raised, or documented out of scope. Silent
wrong output is the only forbidden outcome.

Auth and credentials

- No credentials: actionable error; `peek` on an already-cached table works.
- Token present but password path needed: error explains why.
- Wrong or expired credentials: mapped from the real envelope, no retry.
- Special characters and whitespace in env values: normalized and tested.
- Redaction everywhere (D8 list); one test asserts it on the fixture capture
  tooling.
- Host-scoped credentials: wrong host fails with a clear message.

API behavior

- Envelope inspection before parsing; unknown envelope shapes raise with the
  raw status block quoted.
- Result too large: detected, actionable error (D3), never a truncated table.
- Maintenance HTML instead of JSON: useful error, not a JSONDecodeError.
- Version drift: changed envelope or ffcsv layout fails loudly (the UBA
  `_check_layout` pattern, ported).
- Sequential requests only (D7).

Payload and parsing

- Zip: empty, multiple members, unexpected names, decompressed-size cap.
- Encodings: ladder reused; test utf-8 and BOM variants too.
- Markers: `-` is zero; `. ... / x ()` are null-like; quality flags pinned by
  fixture. Zero-vs-missing gets a dedicated test per recipe.
- Numbers: decimal commas, thousands dots, negatives, int64 counts never via
  float, empty trailing cells.
- Time labels: every frequency present in the chosen tables; unexpected label
  raises with the label.
- Empty result: typed empty table with the declared schema; `peek` shows
  columns.
- Duplicate or extra columns: raise (layout drift).

Region keys and mapping

- Leading zeros: strings end to end; Excel-mangled integer keys (01001 as
  1001) are repaired only when unambiguous by level and length, else raise.
- Levels: 2, 5, 8 digit AGS and 12-digit ARS detected; mixed levels in one
  input raise.
- City-states (Berlin, Hamburg, Bremen's two cities) treated consistently.
- Gemeindefreie Gebiete: covered by the unmatched-key report.
- Reforms (mergers, splits, renames, key reuse): the mapper never assumes a
  key means the same thing in two editions. Test case: a documented 2021
  Kreis merger, verified against GV-ISys before the test is pinned.
- Unmatched keys: structured report, fail-loud default, flagged pass-through
  option.
- Crosswalk quality: share sums within tolerance; duplicated pairs; zero-share
  rows; direction asserted from the key file's own metadata in a fixture test.
- Edition mismatch: data year outside key coverage raises with the range; the
  "partially validated" LAU table is a documented caveat.
- NUTS version drift: outputs name their version; joining across versions
  raises.

Time series and freshness

- Frequency mismatch on join: explicit error, no implicit aggregation.
- Census breaks: documented in recipe notes; the flag column leaves room for a
  series-break marker.
- Upstream revisions: D6 (cache hit wins, warning after 30 days, `refresh`).

Operational

- Offline by default; cache misses raise a clear network error naming the
  URL.
- No credentials in CI or on fork PRs: live tests skip visibly.
- Corrupted cache entries re-download (M1 behavior).
- New dependency (openpyxl) respects exclude-newer and passes pip-audit.

## 7. Test strategy

1. Fixtures first (week 1): one small ffcsv zip per recipe candidate, the
   error envelopes, and one small extract per reference-data source, captured
   by tooling that redacts credentials, committed with the D9 `NOTICE`.
2. Unit and contract: respx-mocked client tests (auth paths, envelope
   mapping, retry, cache keying with credential exclusion, the D7 lock);
   parser tests pinned to fixtures; hypothesis properties for share sums,
   string-key preservation, level detection, and period round-trips.
3. Integration: `mloda.run_all` end to end against fixtures for every recipe;
   the Land-level cross-portal join as the flagship test; `live`-marked smoke
   (whoami, one tiny table) run manually per D8.

## 8. Schedule, checkpoints, cut lines

Weeks are Mon-Sun. Biweekly funder updates fall on Mondays; each Friday's
state is the update material. Exact update dates are tracked in the planning
companion.

- **Week 0 (Aug 14 to 16):** plan reviewed; live `whoami`; recipe-candidate
  tables checked for size and host (GENESIS-Online vs Regionalstatistik), the
  single riskiest unknown; GitHub issues per WP opened.
- **Week 1 (Aug 17 to 23):** WP-A auth, endpoint verification, envelope
  characterization; fixture capture tooling and the committed fixture set,
  including the reference-data extracts (WP-D does not wait for the
  connector); the WP-B fetch seam.
- **Week 2 (Aug 24 to 30):** WP-B tablefile pull, POST cache, ffcsv parser,
  `DestatisReader` on fixtures; first live pull. **Checkpoint C1 (Aug 30):**
  a real GENESIS table arrives as a typed Arrow table via `mloda.run_all`. If
  C1 is red, WP-C, WP-E integration, and WP-F wait; WP-D continues (it is
  standalone).
- **Week 3 (Aug 31 to Sep 6):** WP-C detection; second table wired; recipe
  format and Feature-to-JSON writer; period model parsers (pure functions).
- **Week 4 (Sep 7 to 13):** WP-D loaders, Kreis mapping, edition model,
  unmatched-key report.
- **Week 5 (Sep 14 to 20):** WP-D BBSR keys; WP-E re-basing. SciCAR
  (Dortmund, Sep 17 to 18) takes two days for interviews; the week is planned
  at three working days. **Checkpoint C2 (Sep 20):** the U2 scenario runs
  (re-based multi-year Kreis series, flagged, edition-pinned). If red, pull
  cut line 3.
- **Week 6 (Sep 21 to 27):** WP-E FeatureGroups; WP-F recipes including
  retrofits and the Land-level cross-portal recipe; docs and demo.
- **Sep 28 to 30:** acceptance walkthrough against section 1; planning-repo
  status flips. Stretch items only if everything above is green.

Cut lines, in the order they are pulled:

1. The Land-level cross-portal recipe becomes a Destatis-only two-table join
   (recipe 3 still exists; the "cross-portal" claim moves to AP3).
2. Quarter and month period parsing drop; annual only for M2.
3. mloda FeatureGroup wrappers for harmonization drop to "pure module plus a
   worked notebook example"; the M2 harmonization claim is carried by the
   module and its tests.
4. The three M1 retrofits shrink to one worked retrofit plus a documented
   template for the other two.

Stretch, only after acceptance is green: full job path, Gemeinde-level
mapping, Regionalstatistik host, discovery helper.

Never cut: compliance fields in recipes, zero-vs-missing tests, flags on
harmonized values, `tox` green. A smaller honest M2 beats a wider silent one.

## 9. Open questions (owner: this plan, resolve in the week named)

- Week 0: which host serves the recipe tables; exact table codes for recipes
  1 and 2.
- Week 1: exact auth mechanism, envelope shapes, ffcsv quality-flag layout,
  zip member layout, whether `regionalkey` selection works on `data/tablefile`
  for the chosen tables.
- Week 4: which NUTS version the current Destatis regional series align to
  (exposed as the edition parameter either way).
- Week 5: whether the first user interviews (5 to 8, planning repo) run at
  SciCAR or move to AP3.

## 10. Out of scope for AP2

New data sources beyond Destatis; resampling or aggregation across
frequencies; seasonal adjustment; a no-code or web interface; scheduled live
CI against any portal; bulk mirroring of whole statistics; pystatis interop
shims; Kreis-level cross-portal joins (no AGS in M1 sources); UBA
station-to-region mapping.

## References

- M1 chassis: `mloda_plugin_govdata/feature_groups/govdata/` and
  `docs/adding-a-reader.md`.
- mloda: `load_features_from_config` (JSON), `ParallelizationMode` default
  SYNC; registry guides feature-group-patterns 02, 03, 04, 08, 11, 26, 27.
- GENESIS-Online RESTful/JSON API, Anwenderdokumentation v5.0 (06.05.2025).
- Eurostat NUTS/LAU correspondence tables (CC-BY-4.0); Destatis GV-ISys; BBSR
  Umsteigeschluessel (dl-de/by-2-0, attribution "Laufende Raumbeobachtung des
  BBSR").
- Private planning companion: `planning/ap2-execution-notes.md`,
  `planning/research/`, `decisions/`, `learnings/`.
