# AP2 implementation plan: Destatis connector and harmonization

Status: draft v2.2, 2026-08-16 (v2 plus the slice-0 OpenAPI assessment in
section 5 WP-A, plus the slice-0 paper work: recipe tables and hosts pinned,
Regionalstatistik in scope, U2 change named, C2 on paper, cut line 2
pre-pulled; details in the checklist and the planning repo `learnings/`).
Living document until M2 (30 Sep 2026): update it when a checkpoint or cut
line moves. Budget, funder-update dates, capacity
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
- Every request except `helloworld/whoami` needs auth (PDF 2.1.3). The
  OpenAPI spec and PDF 2.4.6 declare `catalogue/qualitysigns` without
  credentials too; whether it really runs unauthenticated is a live check in
  slice 0, not an assumption. `job=true` and `profile/*` calls need username
  plus password; the token is not accepted there. Dual-path credentials are
  a verified constraint.
- POST-only API since 15 Jul 2025 (SOAP and the REST GET variants are gone;
  only `whoami` and `catalogue/qualitysigns` still answer GET). Third-party
  examples predate this; the Anwenderdokumentation v5.1 (01.06.2026) is the
  contract. `pyproject.toml` still says "GENESIS API v3"; fix in WP-G.
- Base URL is `https://genesis.destatis.de/genesisWS/rest/2020/` (week 0,
  verified: `www-genesis.destatis.de` answers with a 307 to it). Credentials
  travel as HTTP headers `username` and `password`; body credentials are
  ignored and the call runs as guest `GAST`. `whoami` is GET-only,
  `catalogue/qualitysigns` answers GET and POST, everything else is POST
  with `application/x-www-form-urlencoded`.
- Documented limits: a cap on parallel requests (value not fixed), server-side
  termination of requests over 15 minutes, `pagelength` max 25000. No
  per-day quota is documented.
- `data/tablefile` formats: csv, datencsv (default), ffcsv, xlsx, genml, html;
  CSV variants arrive zipped. ffcsv has fixed English headers and is the tidy
  choice. Quirks remain: windows-1252, semicolons, decimal commas, value
  markers. The M1 encoding ladder and marker sets apply (`core/parse.py`:
  `-` is zero, `. ... / x ()` are null-like), with one Destatis-specific
  rule from week 0: the raw sign is kept next to the typed value, because
  GENESIS writes `-` both for a genuine "nothing present" and for a Kreis
  outside its Gebietsstand validity (section 6, WP-B).
- Week 0 (2026-08-16), the host question: GENESIS-Online serves exactly 31
  Kreis-level tables and none of them is a labor-market or income table;
  those live on Regionalstatistik (`www.regionalstatistik.de`, same
  webservice software, same API contract for our endpoints, own free
  registration and token, run by IT.NRW). Recipe 2 therefore pulls
  Regionalstatistik into WP-A scope; recipes 1 and 3 stay on GENESIS-Online.
  The web UIs of both hosts have an unauthenticated JSON backend
  (`genesis.destatis.de/genesis/api/rest/...`,
  `www.regionalstatistik.de/gngServer/api/rest/...`) that answered every
  paper-work question (table lists, structures, values) while the webservice
  was degraded; it is a characterization tool, not a connector target.
- kerg.csv Land rows (`gehört zu = 99`) carry the Land AGS-2 in `Nr`
  (`11;Berlin;99`), the Bundesgebiet row is `99;Bundesgebiet;` with an empty
  `gehört zu` (verified on the full btw25 file, 299 + 16 + 1 rows).
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
  names (`value`, `value_unit`, `value_variable_code`, `value_q`, `time`,
  `1_variable_attribute_code`, ...; the current long format, confirmed
  offline in week 0 from Destatis' own example files), plus the reader's
  `value_marker` column, one locator per table selection. Measure and region
  selection happen in the locator, not in feature names. Harmonized, application-style names
  (`destatis__bevoelkerung__kreise`) are derived FeatureGroups in WP-E; ASCII
  rule: ä/ö/ü/ß become ae/oe/ue/ss.
- **D2 Cross-portal join level.** M1 sources carry no AGS: `kerg.csv` keys on
  Wahlkreis number (`Nr;Gebiet;gehört zu`), UBA keys on `station_id`. The AP2
  cross-portal recipe joins Destatis population with Bundestagswahl results at
  Land level: kerg rows with `gehört zu = 99` are the Land rows and their
  `Nr` already is the Land AGS-2 that Destatis' `DLAND` uses (verified in
  week 0 on the full file), so the join key is `Nr` = `DLAND` and the 16-row
  Land-to-AGS-2 constant is a name check on those rows, not the join path.
  Kreis-level cross-portal joins and UBA station-to-region mapping are out
  of scope for AP2.
- **D3 Job path.** M2 scope is detection of the "result too large" envelope
  plus an actionable error (why the password path is needed, how to shrink
  the selection, how to fetch manually). The full submit/poll/download/remove
  path is stretch. Recipes are chosen small enough not to need it.
- **D4 Mapping level.** Kreis (5-digit AGS) is M2 scope. Gemeinde (8-digit)
  and 12-digit ARS are stretch; the data model keeps keys as strings so the
  levels can be added without migration.
- **D5 Hosts and discovery.** The base URL is a field on the locator with
  GENESIS-Online as default. Regionalstatistik is a second implemented host
  since week 0 (recipe 2 lives there): same client, host-scoped credentials
  (own registration and token), its own pinned spec fixture and contract
  test, its own live smoke. The Zensus database is not implemented and not
  designed beyond the base-URL field. No catalogue/discovery helper in AP2;
  recipes name table codes. (The slice-0 OpenAPI assessment considered
  pulling a typed helper into slice 4 and kept it out under this rule; WP-A
  records what is captured instead.)
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

- Endpoints in scope (verified against doc v5.1 and the pinned OpenAPI spec
  in week 0): `helloworld/whoami` (GET), `helloworld/logincheck`,
  `data/tablefile` (25 form fields: `name`, `area`, `compress` (suppresses
  empty rows and columns; the zip download is unconditional), `transpose`,
  `contents`, `startyear`, `endyear`, `timeslices`, `regionalvariable`,
  `regionalkey`, `classifyingvariable1..5`, `classifyingkey1..5`, `format`,
  `quality` (in the spec, absent from the PDF), `job`, `stand`, `language`),
  `catalogue/qualitysigns` (GET, fixture source for the value-marker legend,
  see WP-B), and for the stretch job path `catalogue/jobs`,
  `data/resultfile`, `profile/removeResult` (camelCase in the spec and in
  the PDF's URL, section 2.7.2; the prose in 2.1.3 writes it lowercase).
- OpenAPI spec, assessed in slice 0 (2026-08-16), pinned in the planning
  repo (`planning/research/genesis-openapi-GOJsonApi-2026-08-16.json`,
  sha256 `1a0dc57a...`). What it is: 45 paths, 46 operations (44 POST, 2
  GET), 110 component schemas; `servers` is the relative `/genesisWS`, so
  the host stays client configuration; `username` / `password` are header
  parameters (default `GAST`) on 43 operations and absent on `whoami` and
  the two `qualitysigns` operations; every request input is a string with
  no description, enum, or `required`; every response is `default` (no HTTP
  status codes); the four `*file` operations declare
  `application/octet-stream` with a generic `Response` object that says
  nothing about the zip or the JSON error body; the 36 JSON operations
  share `Ident {Service, Method}`, `Status {Code: int, Content, Type}`, an
  endpoint-specific `Parameter` (all 33 `*Parameter` schemas declare
  `username` and `password`), `Copyright`, and `Object` or `List` or
  neither (`RemoveResult`, `Password`); `LoginCheck {Status: str,
  Username}` and `HelloWorldInformation {User-Agent}` are flat; catalogue
  rows are typed via `AbstractCatalogueEntry {Code, Content}` plus a few
  strings (`TableCatalogueEntry` adds `Time`, `Valid`); `metadata/table` is
  typed down to the recursive `StructureElement`. What it is used for,
  decided:
  (a) an offline contract test in slice 2 (about 2 h, replaces the manual
  endpoint check): the full spec is a test fixture with a `NOTICE`; for
  every operation `GenesisClient` implements, assert exact path and method,
  the header credential declaration, that every form field the client can
  send is declared on that operation's request body (never derived from a
  response `Parameter` schema: `JobCatalogueParameter` lists `area`, the
  `catalogue/jobs` request body does not), and the defaults the client
  relies on (`format` `datencsv`, so `ffcsv` is always sent explicitly;
  `quality` `off`; `job` `false`; `language` `de`; `area` `free`, which
  the client does not send). Response shapes and HTTP
  status codes stay fixture-based; the spec has neither. The client is
  hand-written over the M1 httpx client, not generated from the spec (no
  auth scheme, no enums, string-only inputs, the `Response` leak, and the D7
  lock, redaction, and typed exceptions are hand-written anyway).
  (b) D10 envelope models (slice 2) take `Status` and `Ident` from the
  spec, one model per reply shape, never one generic parser keyed on the
  field name `Status` (a string on `LoginCheck`, an object elsewhere);
  `Object` / `List` optional; `Parameter` kept as a string map with
  `username` and `password` stripped at parse time (the PDF examples mask
  them, the observed `logincheck` echo is real, assume real); `Type`
  compared case-insensitively (`ERROR` observed, `Error` documented, no
  enum in the spec); the flat tablefile error body (HTTP 404 observed) is
  modelled from observation.
  (c) `docs/destatis-options.md` (slice 4, about 2 h counted under WP-G):
  one table for `data/tablefile` (parameter, spec default, allowed values
  with the PDF section cited, `DestatisLocator` field or the pinned wire
  value or "not exposed in M2" with the reason), plus a paragraph each on
  `whoami` / `logincheck` and on `qualitysigns`.
  (d) the discovery helper stays stretch (D5); slice 2's capture script
  also records `metadata/table` for each pinned table (its
  `Structure.Rows[].Code` names the regional variable, PDF 2.6.3 example
  `DLAND`) and one `catalogue/qualitysigns` reply, so slice 4 configures
  `regionalvariable` from a fixture and the marker legend exists offline.
- Second host, Regionalstatistik (week 0, 2026-08-16): base URL
  `https://www.regionalstatistik.de/genesisws/rest/2020/` (lower-case
  `genesisws`; its spec's `servers` says so), spec pinned in the planning
  repo as `genesis-openapi-regionalstatistik-GOJsonApi-2026-08-16.json`
  (sha256 `a9ce7944...`): 45 paths, 48 operations (GET still declared on
  `profile/password` and `profile/removeResult`), request side identical to
  GENESIS-Online for `whoami`, `logincheck`, `data/tablefile`,
  `metadata/table`, `catalogue/qualitysigns` (only `data/chart2table` and
  `data/table` differ), response schemas generated by an older tool, so the
  contract test compares request sides only and runs once per pinned spec.
  Registration is separate and free (own token; the GENESIS-Online token is
  not valid there); user service regionaldatenbank@it.nrw.de. The
  host-prefixed env variants below are what selects the credential set.
- `DestatisCredentials`: explicit option, then env (`GENESIS_TOKEN`,
  `GENESIS_USER`, `GENESIS_PASSWORD`; host-prefixed variants, for example
  `REGIONALSTATISTIK_TOKEN`, resolved from the locator's host). Whitespace
  normalized. Never logged, never in cache keys, metadata, recipes, snapshots,
  or fixtures.
- POST request layer: form-encoded body, credentials in the `username` and
  `password` HTTP headers (doc v5.1 and week-0 observation; the token goes
  in `username` with an empty `password`), `language` pinned per request,
  the D7 lock. A `logincheck` reply of `Username: GAST` means the headers
  were not sent; treat it as an auth failure, never as success.
- Error envelope: three shapes seen or documented, characterized in week 1
  (bad credentials, unknown table, empty selection, too large, job
  accepted): `helloworld/*` flat `Status` plus `Username` in HTTP 200; the
  documented data shape `Status: {Code, Content, Type}` plus `Parameter`,
  `Object`, `Copyright`; and a flat top-level `Code`, `Content`, `Type` with
  HTTP 404 (observed for an unauthenticated `data/tablefile`). The spec
  confirms the nested `Status` object (`Code` integer) and the flat
  `LoginCheck` reply, and declares no HTTP status codes. Mapped to
  typed exceptions with the HTTP status inspected too. The generic
  "unerwarteter Systemfehler" text is what the backend returns during an
  outage and, as observed, also for guest or wrong credentials; it maps to
  a "backend error, retry later, then check credentials in the web UI"
  exception, never to bad credentials alone. Missing credentials error
  names the env vars and says registration is free and same-day, with the
  URL. Auth failures are not retried.

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
  count and names), decompressed-size cap. Wire policy: every value is sent
  as a string (the spec types every input as string; booleans as `true` /
  `false`, years as `jjjj`); `format=ffcsv`, `language`, `job=false`,
  `quality`, `compress=false`, and `transpose=false` are always sent
  explicitly because their server defaults shape the payload; `area`,
  `stand`, `timeslices`, and unset selection fields are not sent, so the
  server defaults apply (`area` in particular: spec default `free`, PDF
  2.5.12 lists `Alle` and `Katalog/Öffentlich`, the examples send `all`;
  not sending it avoids guessing).
- ffcsv shape, known offline since week 0 from Destatis' own example zip
  (`docs/Aenderung_Struktur_Flatfile-CSV.zip`, Sept 2024, sha256 `46c5bb2f...`,
  the same file on both hosts): fixed prefix `statistics_code;
  statistics_label; time_code; time_label; time`, then N blocks
  `{N}_variable_code; {N}_variable_label; {N}_variable_attribute_code;
  {N}_variable_attribute_label`, then `value; value_unit;
  value_variable_code; value_variable_label; value_q`. Long format, one row
  per (time, attributes, value variable, unit); the same `value_variable_code`
  can occur with two units (`PREIS1` as `2020=100` and as `%`), so the row
  key includes `value_unit`. utf-8 with BOM, LF line endings, semicolon,
  decimal comma in `de`, one CSV member per zip. Markers sit in the `value`
  cell (`-`, `.` seen) with `value_q` empty; `value_q` otherwise `e` or `()`.
  The old format (German wide headers `Statistik_Code; ...;
  <CODE>__<Label>__<Unit>`) is in the same zip and is the layout-drift
  fixture. Live-only remainder: the `time` format for `STAG` tables, `value_q`
  under `quality=off`, webservice zip member names, `language=en` decimals.
- ffcsv parser in `destatis/core/parse.py`: import the encoding ladder,
  dialect, decimal-comma and marker handling from `govdata/core/parse.py`;
  add the English header contract, time column parsing (delegated to the
  WP-E period model), quality-flag columns if present. A column that cannot be
  typed raises with the offending cell. The value-marker legend is the
  `catalogue/qualitysigns` fixture (PDF 2.4.6: `0`, `-`, `...`, `/`, `.`,
  `x`, `()`, `p`, `r`, `s`); a test pins M1's `ZERO_MARKERS` and
  `NULL_MARKERS` against it, and `p`, `r`, `s` are flags, never values.
  Destatis rule (week 0): the parser emits `value_marker` (the raw sign of
  the value cell, empty for numeric cells) next to the delivered `value_q`
  on every Destatis table, because GENESIS writes `-` ("nichts vorhanden")
  both for a real zero count and for a Kreis outside its Gebietsstand
  validity (`03159 Göttingen` before 2016, `03152` and `03156` after 2016, on
  both hosts). `-` still parses to 0 and `. ... / x ()` to null; nothing is
  lost, and the harmonization step, which knows validity windows, is the
  place that turns a `-` outside validity into "not applicable" (section 6).
- `DestatisLocator`: table code (`12411-0015` style), optional region and
  classifying selection, optional `contents` (measure codes; D1 puts
  measure selection in the locator), start/end year, `quality` (bool,
  default off), host, language, format pin; `from_string` accepts a bare
  table code. `area`, `compress`, `transpose`, `timeslices`, `job`, and
  `stand` are not locator fields in M2; `docs/destatis-options.md` says
  which wire value each is pinned to and why.
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
  as a fixture (D9). BBSR Kreis file, characterized in week 0
  (`ref-kreise-1990-2024.xlsx`, sha256 `68c4d001...`): 34 sheets named
  `1990-1991` to `2023-2024`, one per consecutive year pair, forward
  direction; columns source key, source name, area / population / employee
  share, area, population, SvB weights, target key, target name; keys are
  8-digit ARS-style numbers with the leading zero lost by Excel (`1001000`
  is Kreis `01001`); trailing empty rows; and two sheets (`2014-2015`,
  `2015-2016`) carry stale fractional shares on identity rows of `07135` and
  `07137` (per-source sums 0.983 and 0.017), so the share-sum check is
  scoped to the keys being re-based and the defect is recorded as a known
  fixture. GV-ISys yearly change files (`Namens-Grenz-Aenderung/<year>.xlsx`)
  list Kreis-level changes with change id, old and new key, and effective
  date; the 2016 file confirms the U2 change below.
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
  with parsers for GENESIS time labels (annual only for M2: cut line 2 was
  pre-pulled in week 0 because every pinned table is annual, `STAG` 31.12.
  or `JAHR`; quarter and month parsing return only if a live payload forces
  it) and for the M1 time columns. Join at equal frequency only; mismatch
  raises with resampling guidance.
- Re-basing: BBSR proportional keys onto a target Gebietsstand; explicit
  direction and key edition, documented rounding, share-sum check with
  tolerance (renormalize inside, raise beyond; scoped to the source keys in
  the request, see WP-D). Every re-based value carries a flag column; census
  breaks (2011, 2022) are noted, not smoothed. Cells whose key is outside its
  Gebietsstand validity (GENESIS writes `-` there) are excluded and reported,
  never summed as 0.
- The U2 change, named and verified in week 0 (2026-08-16): Landkreis
  Göttingen 2016. `03152 Göttingen, Landkreis` and `03156 Osterode am Harz,
  Landkreis` merged into `03159 Göttingen, Landkreis` on 01.11.2016
  (GV-ISys change `03/2016/0006-R`, Kreis level; BBSR sheet `2015-2016` maps
  both to `03159` with share 1 for area, population and employees; GENESIS
  labels say `(bis 31.10.2016)`). Fallback: Eisenach `16056` into
  Wartburgkreis `16063`, 01.07.2021 (BBSR sheet `2020-2021`). Fractional
  case for the share arithmetic: Cochem-Zell `07135` in BBSR sheet
  `2013-2014` (0.9828486 population share stays, 0.0171514 to `07140`).
  C2 on paper: source `12411-0015`, `regionalkey=03152,03156,03159`, years
  2013 to 2017, target Gebietsstand 31.12.2016, population-proportional key,
  direction 2015 to 2016; expected re-based `03159` = 322,616 (2013),
  324,013 (2014), 329,538 (2015), observed 327,065 (2016), 328,036 (2017);
  fractional check `07135` 2013 = 63,202 becomes 62,118 with 1,084 moving to
  `07140` (100,770 becomes 101,854). Full table in the planning repo
  learning; it becomes the slice 9 expected-value fixture.
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
- Three new recipes (tables pinned in week 0, 2026-08-16; all sized to skip
  the job path): (1) population by Kreis over time: GENESIS-Online
  `12411-0015` Bevölkerung: Kreise, Stichtag (`KREISE`, `STAG` 1995 to 2025,
  contents `BEVSTD`; 477 keys incl. 75 dissolved ones, Berlin `11000`), the
  U2 re-basing scenario over `03152`, `03156`, `03159`; (2) a Kreis-level
  labor-market indicator: Regionalstatistik `13211-02-05-4` Arbeitslose nach
  ausgewählten Personengruppen sowie Arbeitslosenquoten, Jahresdurchschnitt
  (ab 2009), Kreise (`KREISE` 490 keys incl. Berlin `11000`, `JAHR` 2001 to
  2025, contents `ERWP06` Arbeitslose in Anzahl and `ERWP10` Quote in %),
  the U1 rate-with-denominator scenario in one file (GENESIS-Online-only
  fallback if that host fails: `12521-0040` Ausländer: Kreise over
  `12411-0015`); (3) Destatis population by Land, GENESIS-Online `12411-0010`
  Bevölkerung: Bundesländer, Stichtag (`DLAND`, 16 keys, Berlin `11`, `STAG`
  1958 to 2025), joined with Bundestagswahl results by Land (D2, join key
  kerg `Nr` = `DLAND`), the U3 and Demo Day scenario.
- Three M1 retrofits (population, elections, UBA) authored and tested as
  recipe files. Not free: budgeted here.

### WP-G: Docs, demo, handoff (about 20 h, woven through)

README Destatis section, `docs/adding-a-reader.md` extension for the
Destatis path, credential setup doc, `docs/destatis-options.md` (the
`data/tablefile` option table from WP-A item (c), authored in slice 4,
about 2 h of this budget), demo notebook chapter, `pyproject.toml`
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
- Spec drift: the pinned OpenAPI spec is a fixture; the contract test fails
  when the client sends a field the operation does not declare, or when a
  re-pinned spec drops or renames anything the client uses. Request fields
  are never derived from response `Parameter` schemas.
- Credential echo: `Parameter.username` and `Parameter.password` in every
  JSON reply are stripped before anything is logged, cached, or committed.
- Sequential requests only (D7).

Payload and parsing

- Zip: empty, multiple members, unexpected names, decompressed-size cap.
- Encodings: ladder reused; test utf-8 and BOM variants too.
- Markers: `-` is zero; `. ... / x ()` are null-like; the marker sets are
  pinned to the `qualitysigns` fixture, so a new sign in a re-captured
  fixture fails the test; quality flags pinned by fixture. Zero-vs-missing
  gets a dedicated test per recipe. Destatis addition: the raw sign always
  survives in `value_marker`, and a `-` for a key outside its Gebietsstand
  validity is "not applicable", decided by the harmonization step from
  validity windows (GV-ISys, BBSR), never by the parser; the per-recipe
  zero-vs-missing test uses `03159` before 2016 as that case.
- Numbers: decimal commas, thousands dots, negatives, int64 counts never via
  float, empty trailing cells.
- Time labels: every frequency present in the chosen tables; unexpected label
  raises with the label.
- Empty result: typed empty table with the declared schema; `peek` shows
  columns.
- Duplicate or extra columns: raise (layout drift).

Region keys and mapping

- Leading zeros: strings end to end; Excel-mangled integer keys (01001 as
  1001, and the BBSR Kreis file's 8-digit `1001000` for `01001`) are
  repaired only when unambiguous by level and length, else raise.
- Validity windows: a key's Gebietsstand validity comes from GV-ISys and the
  BBSR key files, not from labels (GENESIS-Online suffixes dissolved Kreise
  with `(bis DD.MM.YYYY)`, Regionalstatistik does not).
- Levels: 2, 5, 8 digit AGS and 12-digit ARS detected; mixed levels in one
  input raise.
- City-states (Berlin, Hamburg, Bremen's two cities) treated consistently.
- Gemeindefreie Gebiete: covered by the unmatched-key report.
- Reforms (mergers, splits, renames, key reuse): the mapper never assumes a
  key means the same thing in two editions. Test case: a documented 2021
  Kreis merger, verified against GV-ISys before the test is pinned.
- Unmatched keys: structured report, fail-loud default, flagged pass-through
  option.
- Crosswalk quality: share sums within tolerance for the source keys being
  re-based (raise), reported for the rest of the sheet (the real BBSR file
  has two sheets with stale fractions on unrelated keys, week 0); duplicated
  pairs; zero-share rows; direction asserted from the key file's own metadata
  (sheet name and header years) in a fixture test.
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

- **Week 0 (Aug 14 to 16):** plan reviewed; OpenAPI spec assessed (done
  2026-08-16, decisions in section 5 WP-A); recipe tables pinned and their
  hosts checked (done 2026-08-16: recipe 2 lives on Regionalstatistik, that
  host is in WP-A scope, section 5 WP-F); U2 change named and C2 written on
  paper (WP-E); cut line 2 pre-pulled; GitHub issues per WP not opened
  (owner decision: fork only for now); live `whoami` and `logincheck` last,
  when the webservice answers (it was degraded on Aug 16), at the latest
  before slice 2. Sizes: `12411-0015` is 31 x 477 cells, `12411-0010` 68 x
  16, `13211-02-05-4` about 25 x 490 x 7 measures; none needs the job path.
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
2. Quarter and month period parsing drop; annual only for M2. **Pulled in
   week 0 (2026-08-16):** every pinned table is annual; the freed slice 7
   hours are banked buffer. Reversible at C1 if a live payload forces it.
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

- Week 0: resolved 2026-08-16. Hosts and codes: `12411-0015` and
  `12411-0010` on GENESIS-Online, `13211-02-05-4` on Regionalstatistik
  (section 5 WP-F); the OpenAPI question: section 5 WP-A; the U2 change and
  C2 cells: section 5 WP-E; cut line 2: pulled.
- Week 1: successful `logincheck` (auth mechanism itself is confirmed by doc
  v5.1, both specs, and the header echo), envelope shapes, `value_q`
  behaviour under `quality=off`, the `time` format of `STAG` tables, zip
  member names from the webservice, whether `regionalkey` selection works on
  `data/tablefile` for the chosen tables (and on the Regionalstatistik host
  once its token exists); whether the live `Parameter` echo is masked or
  real; whether `catalogue/qualitysigns` runs without credentials. The ffcsv
  column layout itself is known from Destatis' example files (WP-B) and only
  needs confirming.
- Week 4: which NUTS version the current Destatis regional series align to
  (exposed as the edition parameter either way).
- Week 5: whether the first user interviews (5 to 8, planning repo) run at
  SciCAR or move to AP3.

## 10. Out of scope for AP2

New data sources beyond Destatis (Regionalstatistik counts as the GENESIS
family under D5, the Zensus database does not); resampling or aggregation
across frequencies; seasonal adjustment; a no-code or web interface; scheduled live
CI against any portal; bulk mirroring of whole statistics; pystatis interop
shims; Kreis-level cross-portal joins (no AGS in M1 sources); UBA
station-to-region mapping.

## References

- M1 chassis: `mloda_plugin_govdata/feature_groups/govdata/` and
  `docs/adding-a-reader.md`.
- mloda: `load_features_from_config` (JSON), `ParallelizationMode` default
  SYNC; registry guides feature-group-patterns 02, 03, 04, 08, 11, 26, 27.
- GENESIS-Online RESTful/JSON API, Anwenderdokumentation "Webservice/API"
  v5.1 (01.06.2026), served by the web UI at
  `https://genesis.destatis.de/datenbank/online/docs/GENESIS-Webservices_Einfuehrung.pdf`
  (English: `GENESIS-Webservices_Introduction.pdf`). Sections used by this
  plan: 1.7, 2.1.2, 2.1.3, 2.2, 2.4.6, 2.4.10, 2.5.12, 2.6.3, 2.7.2.
- GENESIS OpenAPI 3.0.1 spec:
  `https://genesis.destatis.de/genesisWS/rest/2020/GOJsonApi.json`; Swagger
  UI: `https://genesis.destatis.de/genesisWS/swagger-ui/index.html`. Pinned
  2026-08-16 in the planning repo as
  `planning/research/genesis-openapi-GOJsonApi-2026-08-16.json`, sha256
  `1a0dc57a85e391b6c7c42de4120156f92a8b0f6a6e10d3e51b8be59536c1e8e6`.
- Regionalstatistik (Regionaldatenbank Deutschland) webservice:
  `https://www.regionalstatistik.de/genesisws/rest/2020/`; spec
  `.../genesisws/rest/2020/GOJsonApi.json`, pinned 2026-08-16 in the planning
  repo as `planning/research/genesis-openapi-regionalstatistik-GOJsonApi-2026-08-16.json`,
  sha256 `a9ce7944d21fc1a9f5330790d9dff939748320486bfb40eadc82608000cd684c`;
  Swagger UI `.../genesisws/swagger-ui/index.html`; own registration.
- Destatis ffcsv example zip (old and new format, PDF with reader code):
  `https://genesis.destatis.de/datenbank/online/docs/Aenderung_Struktur_Flatfile-CSV.zip`,
  sha256 `46c5bb2fd5ad3836a01d57efbd7b755d3d1670b1a42b167b47830c643fda1dc8`
  (2026-08-16).
- Eurostat NUTS/LAU correspondence tables (CC-BY-4.0); Destatis GV-ISys
  (yearly changes:
  `https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/Namens-Grenz-Aenderung/2016.xlsx`,
  sha256 `301a0b72381d78ece5b3fe811fd29e7739258da55ebda9dacb1a0d2651f2b0b7`);
  BBSR Umsteigeschluessel (dl-de/by-2-0, attribution "Laufende Raumbeobachtung
  des BBSR"; Kreise:
  `https://www.bbsr.bund.de/BBSR/DE/forschung/raumbeobachtung/Raumabgrenzungen/umstiegsschluessel/ref-kreise-1990-2024.xlsx`,
  sha256 `68c4d001cc450115938d37c42aa8cc090fb9e6381e7e29d00f049cffdbcc8f1f`,
  fetched 2026-08-16).
- Bundeswahlleiterin btw25 `kerg.csv`, sha256
  `31ab27391d5753a6a972936d436092879f5c9cca11570272cd72e3e272d16731`
  (2026-08-16), the M1 election source.
- Private planning companion: `planning/ap2-execution-notes.md`,
  `planning/research/`, `decisions/`, `learnings/`.
