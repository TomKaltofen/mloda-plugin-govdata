# AP2 implementation plan: Destatis connector and harmonization

Status: draft v1, 2026-08-14. Covers work package AP2 (01 Aug to 30 Sep 2026,
290 budgeted hours) toward milestone M2 (30 Sep 2026): Destatis connector
working, harmonization implemented, 6 recipes total.

Inputs: the M1 codebase in this repo, the verified constraints research in the
private planning companion repo (GENESIS API doc v5.0 findings, harmonization
reference-data survey, license clarifications), and the first-run user research
plan (three target segments).

As of 2026-08-14 no AP2 code exists; roughly 6.5 weeks remain to M2. This plan
is deliberately walking-skeleton biased: a thin Destatis end-to-end path lands
first, depth follows, and every Friday state is demoable for the biweekly
funder updates (Aug 17, Aug 31, Sep 14, Sep 28) and the conference abstract
that must be drafted from early-M2 material by late October.

## 1. Goal and acceptance

M2 acceptance, verbatim from the funding application: Destatis connector
working, harmonization implemented, 6 recipes total.

Interpreted as a checkable definition of done:

1. A `DestatisReader` pulls at least two real GENESIS tables end to end
   (auth, request, download, parse) into typed Arrow tables via the same
   `mloda.run_all` call shape as the M1 readers.
2. The harmonization layer maps AGS region keys to NUTS codes with explicit
   edition/version selection, and re-bases at least one real multi-year series
   across a Gebietsstand change using the BBSR Umsteigeschluessel.
3. Time-series alignment produces a documented, typed period representation
   that joins Destatis data with at least one M1 source.
4. Three new recipes exist (six total), each carrying license, attribution
   string, dataset URI, and modification-marking fields.
5. `tox` green (pytest, ruff, mypy strict, bandit), no live network in the
   default test run, README and demo notebook updated.

## 2. Starting position (what is already settled)

Carried over from M1 and the research phase; none of this is open:

- **Account and token exist** (registered 2026-06-16, token issued same day).
  Still unverified: a live `whoami` call. That is task one of week 1.
- **Dual-path credentials are mandatory.** Every GENESIS request except
  `whoami` needs auth. Requests with `job=true` (the documented path for
  oversized tables) plus `profile/*` calls cannot use the 32-character token
  and need username/password. This is a verified hard constraint, not a
  design choice.
- **POST-only API.** The SOAP interface and REST GET methods were shut down
  15 Jul 2025. Only RESTful/JSON POST remains. Most blog posts and older
  library code predate this; treat third-party examples as stale until
  checked against the v5.0 Anwenderdokumentation.
- **Rate limits:** only a cap on parallel requests is documented (value not
  fixed; Destatis reserves the right to change it) plus auto-termination of
  requests running over 15 minutes. No requests-per-day quota. `pagelength`
  caps at 25000.
- **Delivery formats:** `data/tablefile` offers csv, datencsv (default),
  ffcsv, xlsx, genml, html; all CSV variants arrive zipped. ffcsv has uniform
  English column headers and is the tidy, machine-friendly choice. Residual
  quirks remain: windows-1252, semicolons, decimal commas, statistical value
  markers. The M1 encoding ladder and value-marker table apply.
- **Licensing is clean end to end.** GENESIS data is dl-de/by-2-0. Eurostat
  correspondence and LAU tables are CC-BY-4.0. Destatis GV-ISys permits
  reproduction with attribution. BBSR Referat RS 6 confirmed in writing
  (2026-06-17) that the Umsteigeschluessel are dl-de/by-2-0 like INKAR and may
  be bundled and redistributed; the only hard requirement is visible
  attribution to "Laufende Raumbeobachtung des BBSR". The earlier
  runtime-fetch-only constraint is lifted.
- **The AGS-to-NUTS mapper is net-new work.** No maintained Python library
  does it (2026 survey). Reference inputs are Excel and GV100 fixed-width
  ASCII, not CSV, so the M1 German-CSV parser contributes little here.
- **M1 gave us the chassis:** pooled httpx client with four-part timeouts and
  polite User-Agent, tenacity retries with Retry-After handling,
  content-addressed download cache with conditional-GET revalidation, the
  `BaseGovDataReader` / `ReadFile` integration pattern, `peek`, the
  fixture-first three-level test posture, and the per-source module layout
  documented in `docs/adding-a-reader.md`.

## 3. Users and acceptance scenarios

AP2 scope decisions below are justified against these five users. The first
three are the researched target segments; the last two are operational
personas the repo must serve anyway.

### U1: Data journalist (newsroom, Correctiv-like)

Deadline-driven, Python-capable but not an API archaeologist, works
Germany-wide at Kreis level, must be able to say where every number came from.

Acceptance scenario: "Unemployment and population by Kreis for 2015 to 2024 as
one tidy typed table on current district boundaries, in a handful of lines,
and a colleague reruns it next month and gets the same table or a loud
explanation of what changed." Exercises: connector, harmonization to a single
Gebietsstand, caching, provenance fields.

What U1 must never hit: silent zero-vs-missing confusion (a `-` cell is zero,
a `.` cell is blocked data; a story built on the wrong one is a correction),
or a region silently dropped because its AGS changed in 2021.

### U2: Empirical researcher (DIW-like)

Long time series across territorial reforms, citation and method requirements,
version pinning matters more than convenience.

Acceptance scenario: "Population 1995 to 2024 for all Kreise, re-based to
Gebietsstand 2024 with the BBSR proportional keys, with the method, key
edition, and citation strings exportable for a paper appendix." Exercises: the
Umsteigeschluessel path, edition selection (Gebietsstand, NUTS version, key
vintage), modification marking, deterministic reruns.

What U2 must never hit: an unlabeled re-based value (every harmonized number
must be distinguishable from a reported number), or a crosswalk applied to the
wrong direction (old-to-new vs new-to-old).

### U3: Civic-tech Python user (CorrelAid / pystatis user)

Already solves raw API access, often with pystatis; our differentiators are
harmonization, typed Arrow output, cross-portal composition, and the GovData
side. Most likely early contributor.

Acceptance scenario: "Pull one GENESIS table without learning EVAS internals,
join it with UBA air data by region and month, all typed, then share the pull
as a recipe file." Exercises: cross-source alignment, the recipe format, low
ceremony credentials.

Positioning note: do not rebuild pystatis and do not disparage it. The honest
answer to "why not pystatis" is the layer above raw access: harmonization,
typed output, one declarative interface across GovData, publisher APIs, and
Destatis. Keep that answer true.

### U4: Contributor (adds the next table or recipe)

Must be able to add a Destatis table recipe by following docs, without a
GENESIS account for the fixture-level tests, in under an hour. Exercises:
module seams, fixture tooling, `docs/adding-a-reader.md` extension for the
Destatis path.

### U5: CI and unattended runs

The default test run needs no credentials and no network. Live tests are
opt-in via env-gated markers. Fork PRs (no secrets) must pass. Recorded
fixtures never contain credentials.

## 4. Scope: work packages

### WP-A: GENESIS client and auth (est. 55 h)

New `feature_groups/destatis/core/` alongside the existing govdata core,
reusing `client.py` retry/timeout policy where possible.

Deliverables:

- `DestatisCredentials`: resolved from explicit option, then environment
  (`GENESIS_TOKEN`, `GENESIS_USER`, `GENESIS_PASSWORD`; host-prefixed
  variants for other hosts, see multi-host below). Token path for normal
  calls, password path required for `job=true`. Never logged, never in cache
  keys, never in recipes or snapshots, never in recorded fixtures.
- POST request layer on the pooled client: form-encoded parameters, the
  documented auth header/field convention (verify exact mechanism against doc
  v5.0 in week 1; do not trust older token-as-username folklore), language
  parameter pinned explicitly per request.
- Error envelope handling: GENESIS is expected to return application-level
  status codes inside HTTP 200 bodies. Characterize the real envelope in week
  1 (fixtures for: bad credentials, unknown table, empty selection, result
  too large, job accepted) and map to typed exceptions with actionable
  messages. A missing-credentials error must tell the user that registration
  is free and same-day, with the URL.
- Multi-host by construction: the base URL is part of the locator, with
  GENESIS-Online (www-genesis.destatis.de) implemented and Regionalstatistik
  (www.regionalstatistik.de) and the Zensus database left as configuration
  points, each with separate credentials. Many Kreis/Gemeinde-level tables
  live in Regionalstatistik, so this seam matters even though implementing
  the second host is a stretch goal (see cut lines).
- Politeness: strictly sequential requests, no client-side parallelism,
  jittered backoff (already in the retry layer), Retry-After honored.

### WP-B: Table retrieval and ffcsv parsing (est. 45 h)

Deliverables:

- `data/tablefile` retrieval with `format=ffcsv`, zip unpacking (verify: one
  file per zip or several; characterize), stored through the download cache.
- POST-aware cache extension: the M1 `DownloadCache` keys on GET URL and
  revalidates with conditional GET; GENESIS responses are POST bodies. Extend
  with a deterministic key over host + endpoint + canonically ordered
  parameters, credentials stripped from the key. No conditional revalidation
  on this path; instead an explicit `refresh` escape hatch and a documented
  default (cache hit wins). Published statistics are revised, so `peek` docs
  and the README must say how to force a refetch.
- ffcsv parser in `destatis/core/parse.py`: reuse the encoding ladder,
  semicolon dialect, decimal-comma and value-marker handling from
  `govdata/core/parse.py` (import, do not copy); add what is new: English
  header contract, time/period columns, value-quality flag columns if the
  format carries them (characterize in week 1), long-format guarantees.
  Fail-loud posture as in M1: a column that cannot be typed raises with the
  offending cell, never silently degrades to strings.
- `DestatisReader(BaseGovDataReader)` wired exactly like the M1 readers
  (`_parse` override, `suffix() == (".zip",)` or the unpacked inner suffix,
  `peek` support), so `mloda.run_all([Feature("value", options={DestatisReader:
  locator})], ...)` works identically to the M1 call shape.
- `DestatisLocator`: table code (EVAS-style, e.g. `12411-0015`), optional
  region selection, start/end year, host, language, format pin. String
  coercion like `GovDataLocator.from_string` (a bare table code is enough for
  the default host). Parameter canonicalization gives stable cache keys, the
  same trick as `uba_measures_url`.

### WP-C: Large tables, the job path (est. 25 h)

Oversized selections require `job=true` and password credentials.

Deliverables: trigger detection (the "result too large" envelope), job
submission, polite polling with backoff against the job list, result file
download, and cleanup via the documented removal call so the account's result
store does not fill up. Poll budget bounded (the API kills requests at 15
minutes; our own polling deadline should be configurable and default to a few
minutes with a clear timeout error). If credentials are token-only, the error
must say exactly why the password path is needed and how to provide it.

Scope guard: the three M2 recipes are chosen small enough not to need the job
path (see WP-F), so WP-C is required for correctness and honesty of the
connector, but the recipes do not depend on it. If time collapses, WP-C
degrades to detection plus a documented "how to fetch this table manually"
error, never a hang.

### WP-D: AGS-to-NUTS mapper (est. 60 h)

Net-new, and deliberately a standalone pure-Python module
(`mloda_plugin_govdata/harmonization/`) usable without mloda, wrapped by
FeatureGroups in WP-E. Two reasons: it is independently valuable (nothing on
PyPI does this), and pure functions over small tables are the easiest thing
to test exhaustively.

Deliverables:

- Reference-data loaders: Eurostat NUTS correspondence and LAU-to-NUTS tables
  (xlsx), Destatis GV-ISys (xlsx and GV100 fixed-width ASCII), BBSR
  Umsteigeschluessel (xlsx, Gemeinden and Kreise, 1990 to 2024). All fetched
  at runtime through the existing GET download cache and pinned by URL plus
  sha256; additionally, now that redistribution is confirmed, a small pinned
  extract ships as a package test fixture so U4 and U5 work offline. Excel
  parsing needs an extra dependency (openpyxl or calamine); pick one, justify
  in the ADR, respect the uv exclude-newer supply-chain window.
- The mapping core: AGS to NUTS-1/2/3 for a chosen edition pair, Kreis level
  first (5-digit AGS), Gemeinde level (8-digit) second. Everything keyed as
  strings with preserved leading zeros, everywhere, always (see edge cases).
- Edition model: every mapping call names its Gebietsstand (reference date)
  and NUTS version explicitly, with a documented default of "latest shipped"
  and a loud warning when data year and edition year diverge. Version
  selection is designed, not hardcoded; the current Eurostat tables are NUTS
  2027 / LAU 2025 but that is a fact about today, not a constant.
- Diagnostics as data: mapping returns matched rows plus a structured report
  of unmatched keys (the GERDA finding: official AGS keys sometimes match no
  crosswalk). Default behavior fail-loud with the report; opt-in modes to
  drop or pass through unmatched rows, always flagged.

### WP-E: Time-series alignment and re-basing (est. 40 h)

Deliverables:

- Period model: one documented, typed representation for year, quarter, and
  month periods (period start date plus frequency tag), with parsers from the
  GENESIS time labels (characterize the real ffcsv time column values in week
  1: years, "1. Vierteljahr" style quarters, month names, German date forms)
  and from the M1 sources' time columns. Join-compatibility across sources at
  equal frequency is the acceptance test (U3's UBA join).
- Gebietsstand re-basing: apply the BBSR proportional keys to move a series
  onto a target Gebietsstand. Explicit direction, explicit key edition,
  documented rounding policy, and a check that shares per source region sum
  to 1 within tolerance (renormalize inside tolerance, raise beyond it).
  Every re-based value is flagged in a companion column: this is the
  dl-de/by-2-0 modification-marking requirement turned into a feature, and it
  is exactly what U2 needs for a methods appendix.
- mloda integration: harmonization and alignment as derived FeatureGroups
  over the reader outputs (`input_features` composition), so the calling code
  stays a plain feature list. Read the registry guides before this lands
  (feature-group-patterns 02, 03, 04, 08, 11, 26, 27); the naming scheme for
  chained features (toward the application's `destatis__bevoelkerung__kreise`
  promise) is decided here and recorded in the ADR.

### WP-F: Recipes, six total (est. 30 h)

Define the recipe artifact first, then fill it:

- Recipe format: a JSON document (mloda already loads feature configs; the
  Feature-to-JSON shim is small) carrying the feature list, reader options,
  and the mandatory compliance block: license id, attribution string, dataset
  URI, retrieval timestamp, sha256 of the payload, and modification markers.
  Credentials are never part of a recipe; a recipe declares which credential
  env vars it needs.
- Three new recipes (candidates, to be validated for size and table stability
  in week 1; all chosen to skip the job path):
  1. Population by Kreis over time (GENESIS 12411 family): the U2 scenario,
     exercises re-basing across the 2021 Eisenach merger and friends.
  2. A labor-market or income indicator by Kreis: the U1 scenario, joins with
     recipe 1 for a rate with population as denominator.
  3. A cross-portal recipe joining a Destatis series with an M1 source
     (UBA air quality or the election results) on harmonized region and
     period: the U3 scenario and the Demo Day story, because it shows the
     layer no other tool has.
- The three M1 pulls are retrofitted into the same recipe format (cheap once
  the shim exists) so "6 recipes total" is literal.

### WP-G: Docs, demo, and handoff (est. 20 h, woven through)

README Destatis section mirroring the M1 usage style, `docs/adding-a-reader.md`
extension for Destatis tables, credential setup doc (registration is free and
same-day; that fact removes the biggest onboarding excuse), demo notebook
gaining a Destatis plus harmonization chapter, and planning-repo updates
(milestone status, an ADR for the AP2 architecture decisions, learnings as
they happen: measured job-path behavior, real error envelopes, ffcsv quirks).

Estimated total: 275 h against 290 budgeted, with the difference as explicit
buffer. Two of nine calendar weeks are already gone; the cut lines in section
8 say what falls off first.

## 5. Architecture decisions to record (ADR at first implementation PR)

1. Module layout: `feature_groups/destatis/` (reader, locator, core/auth,
   core/api, core/parse) plus source-neutral `harmonization/` at package
   level. Mirrors the M1 convention: source-specific parse near the source,
   shared logic importable without a reader.
2. Cache: extend, do not replace. GET path untouched; POST path adds
   parameter-keyed entries with explicit refresh, no conditional
   revalidation, credentials excluded from keys and metadata.
3. Credentials: env-first with explicit-option override, dual-path by design,
   host-scoped. No secrets manager dependency in AP2; document the env names
   once and reuse everywhere.
4. Harmonization as data-plus-flags, never in-place mutation: harmonized
   outputs carry marker columns instead of replacing observed values
   silently. Serves U1/U2 trust and the license's modification-marking duty
   simultaneously.
5. Reference data policy: runtime fetch with pinned editions and sha256, plus
   one small redistributable fixture extract per source now that BBSR
   licensing is confirmed. Attribution strings for BBSR ("Laufende
   Raumbeobachtung des BBSR"), Eurostat, and Destatis ship as constants next
   to the loaders.
6. pystatis: considered as a dependency, rejected for AP2 (we need our own
   caching, politeness, typed-Arrow, and mypy-strict posture, and the API
   surface we use is small), revisit if the connector scope grows. Record the
   reasoning so the U3 conversation stays honest.

## 6. Edge-case catalog

The checklist the implementation and its tests are graded against. Grouped;
each item is either handled, detected-and-raised, or explicitly documented as
out of scope. Silent wrong output is the only forbidden outcome.

### Auth and credentials

- No credentials at all: actionable error naming the env vars and the
  same-day registration; `peek` against an already-cached table still works.
- Token present but job path needed: error explains the password requirement
  (verified API constraint, not our whim).
- Wrong or expired credentials: mapped from the real error envelope, no
  retry storm (auth failures are not retryable).
- Special characters in passwords, whitespace around env values: normalize
  and test.
- Credentials must never appear in: logs, exception messages, cache keys,
  cache metadata, recipes, snapshots, recorded fixtures, or the demo
  notebook. One test asserts redaction on the recorded-fixture pipeline.
- Two hosts, two accounts: credential resolution is host-scoped; using
  GENESIS-Online credentials against Regionalstatistik fails with a clear
  message, not a confusing 200-with-error-body.

### API behavior

- Application errors inside HTTP 200 bodies: every response goes through
  envelope inspection before parsing; unknown envelope shapes raise with the
  raw status block quoted.
- Result too large: detected, routed to the job path or a clear error, never
  a truncated table.
- Job lifecycle: queued, running, done, failed, result expired; polling has
  a deadline; results are cleaned up after download; a crashed run does not
  strand results forever (cleanup is attempted on next run, best effort).
- The 15-minute server-side kill and the parallel-request cap: sequential
  requests only; long pulls prefer the job path by design.
- `pagelength` and paging on list-style endpoints (catalogue/discovery):
  paginate lazily like the M1 `search_datasets`, stop conditions tested.
- Maintenance windows and 5xx: existing retry policy with Retry-After cap
  applies; a scheduled-maintenance HTML body instead of JSON must raise a
  useful error, not a JSONDecodeError.
- Language parameter: pinned explicitly; tests assert we never depend on
  server-side default labels (the UBA reader's canonical-schema lesson).
- API version drift: the client sends against one documented version; a
  changed envelope or changed ffcsv layout fails loudly (the UBA
  `_check_layout` pattern, ported).

### Payload and parsing

- Zip handling: empty zip, multiple members, unexpected member names,
  zip-bomb guard (size cap on decompressed bytes, configurable).
- Encodings: ladder reused; ffcsv nominally windows-1252, but test utf-8 and
  BOM variants too.
- Value markers: `-` is zero, `.` `...` `/` `x` `()` are null-like blocks
  (secrecy, not-yet, undefined); ffcsv may also carry quality flags (e, p) in
  companion columns or attached to values; week-1 characterization decides,
  tests pin it. The zero-vs-missing distinction gets a dedicated test per
  recipe because it is the U1 correction scenario.
- Numbers: decimal commas, thousands dots, negative values, huge counts
  (int64, never through float), empty cells at row ends.
- Time labels: all frequencies present in the chosen tables, plus the
  unexpected-label case (raise with the label, do not guess).
- Empty result table (valid selection, no data): typed empty table with the
  declared schema, not an exception, and `peek` still shows columns.
- Duplicate column names, columns beyond the documented contract: detect and
  raise (layout drift), never positional guessing beyond the pinned
  contract.

### Region keys and mapping

- Leading zeros: AGS/ARS are strings end to end; a test feeds an
  Excel-mangled integer key (01001 turned 1001) and asserts the loud repair
  path (left-pad only when unambiguous by level and length, otherwise raise).
- Key levels: 2 (Land), 5 (Kreis), 8 (Gemeinde) digit AGS, 12-digit ARS with
  Verband part; mixing levels in one input is detected.
- City-states: Berlin and Hamburg (and Bremen's two-city split) where Land,
  Kreis, and Gemeinde collapse; mapping tables treat them consistently.
- Gemeindefreie Gebiete and special areas: present in GV-ISys, often absent
  elsewhere; unmatched-key report covers them.
- Reforms: mergers, splits, renames, and the reuse of freed keys; the mapper
  never assumes a key means the same thing in two Gebietsstand editions.
  The 2021 Eisenach-into-Wartburgkreis merger is the canonical test case.
- Unmatched keys (the GERDA 1000+ finding): structured report, fail-loud
  default, flagged pass-through option.
- Crosswalk quality: shares per source region must sum to 1 within
  tolerance; duplicated (source, target) pairs; zero-share rows; the
  direction of every key file (old-to-new vs new-to-old) asserted from the
  file's own metadata in a fixture test, not assumed.
- Edition mismatches: data year outside the key coverage (before 1990 or
  after the latest edition) raises with the covered range; LAU table marked
  "partially validated" by Eurostat is a documented caveat, not silently
  trusted.
- NUTS version drift: mapping output names its NUTS version; joining two
  tables harmonized to different NUTS versions raises.

### Time series

- Frequency mismatch on join (annual vs monthly): explicit error with the
  offered resampling guidance, no implicit aggregation in AP2.
- Census rebasing jumps (2011 and 2022 Zensus revisions of population
  series): not smoothed, but documented in the recipe notes; the flags column
  design leaves room for a "series break" marker.
- Retroactive data revisions upstream: cache default serves the cached
  payload; the recipe's sha256 plus retrieval timestamp make staleness
  visible; `refresh` documented.

### Operational

- No network (plane, CI): default test suite fully offline; runtime cache
  misses raise a clear network error naming the URL.
- No credentials in CI and on fork PRs: live tests skip cleanly with a
  visible skip reason; the suite never half-runs.
- Cache directory shared between GET and POST paths without key collisions;
  corrupted cache entries re-download (M1 behavior, kept).
- Windows: paths, cp1252 consoles, no os-specific test breakage (the fixture
  suite runs on the CI matrix as today).
- Supply chain: new dependencies (Excel reader) respect the 7-day
  exclude-newer window and pass pip-audit.

## 7. Test strategy

Same three-level posture as M1, applied to the new surface:

1. **Fixtures first (week 1 deliverable):** captured real payloads, committed
   before parser code: one small ffcsv table zip per recipe candidate, the
   error envelopes (bad auth, unknown table, empty selection, too large), a
   job-path transcript, and one small extract per reference-data source
   (Eurostat, GV-ISys both formats, BBSR keys). Credentials redacted at
   capture time by tooling, not by hand.
2. **Unit and contract:** respx-mocked client tests for auth paths, envelope
   mapping, retry/backoff, cache keying (including credential exclusion);
   parser tests pinned to fixtures; hypothesis properties for the mapper
   (share sums, string-key preservation, level detection, unmatched-report
   completeness) and for period parsing round-trips.
3. **Integration:** `mloda.run_all` end to end against fixtures for every
   recipe; the cross-source join scenario as the flagship test; env-gated
   live smoke tests (one tiny table, whoami) run manually and before each
   biweekly update, never scheduled (the M1 politeness rule stands until the
   ToS question is formally closed, and there is no CI credential story yet).

## 8. Schedule, checkpoints, cut lines

Remaining calendar: 6.5 weeks (Aug 14 to Sep 30). Weeks are Mon-Sun; the
biweekly funder updates are fixed posts.

- **Week 0 remainder (Aug 14 to 16):** this plan reviewed; ADR skeleton;
  `whoami` verified live; recipe-candidate tables checked for size and
  availability on GENESIS-Online vs Regionalstatistik (this decides whether
  the multi-host stretch becomes mandatory scope, the single riskiest
  unknown in the plan).
- **Week 1 (Aug 17 to 23):** WP-A auth layer plus envelope characterization;
  fixture capture tooling and the committed fixture set; update #6 (Aug 17)
  reports AP2 started with verified API contact.
- **Week 2 (Aug 24 to 30):** WP-B: tablefile pull, POST cache, ffcsv parser,
  `DestatisReader` end to end on fixtures; first live table pull.
  Checkpoint C1 (Aug 30): a real GENESIS table arrives as a typed Arrow
  table via `mloda.run_all`. If C1 fails, everything in WP-C to WP-E freezes
  until it passes; the connector is the milestone's spine.
- **Week 3 (Aug 31 to Sep 6):** WP-C job path; second table/recipe wired;
  discovery helper if cheap; update #7 (Aug 31) shows the end-to-end demo.
- **Week 4 (Sep 7 to 13):** WP-D mapper core with Eurostat plus GV-ISys
  loaders, Kreis level, edition model, unmatched-key report.
- **Week 5 (Sep 14 to 20):** WP-D Gemeinde level plus BBSR keys; WP-E period
  model and re-basing; update #8 (Sep 14) shows the first harmonized series.
  Checkpoint C2 (Sep 20): the U2 scenario runs (re-based multi-year Kreis
  series, flagged, edition-pinned). If C2 is red, invoke cut line 2.
- **Week 6 (Sep 21 to 27):** WP-E mloda FeatureGroups; WP-F recipes finalized
  in the format with compliance fields; cross-source recipe; docs and demo.
- **Week 6.5 (Sep 28 to 30):** M2 acceptance walkthrough against section 1;
  update #9 (Sep 28) is the M2 report; planning-repo status flips.

Cut lines, in the order they are pulled:

1. Regionalstatistik host support drops to "designed, documented, not
   implemented" (unless week-0 table checks force it into scope; then the
   Zensus host takes this slot and one recipe swaps to a GENESIS-Online
   table).
2. Gemeinde-level mapping drops; Kreis-level mapping plus re-basing is the
   M2 harmonization claim (it covers all three recipes and both U1/U2
   scenarios).
3. The job path degrades to detection with a documented manual workaround.
4. The discovery helper (catalogue search) drops entirely; recipes name
   table codes directly.
5. Never cut: the compliance fields in recipes, the zero-vs-missing tests,
   the flags-on-harmonized-values design, and tox green. These are the
   trust surface; a smaller honest M2 beats a wider silent one.

## 9. Risks and open questions

- **Table availability split across hosts** (GENESIS-Online vs
  Regionalstatistik) is the top schedule risk; resolved by the week-0 check,
  hedged by cut line 1.
- **Undocumented envelope or ffcsv surprises:** budgeted via the
  characterization-first week 1; every surprise becomes a fixture and a
  planning-repo learning the day it appears.
- **Capacity:** 275 h of plan against 6.5 remaining weeks is tight but real
  only if the weeks are actually full; the cut lines are ordered so slipping
  degrades breadth, not correctness.
- **Second Stage jury timing** (around September) may demand demo attention
  mid-AP2; the walking-skeleton ordering means there is always a current
  demo, which is also the FOSSGIS abstract hedge (draft due late October,
  from exactly the material weeks 2 to 5 produce).
- Open: which NUTS version the Sep 2026 Destatis regional series effectively
  align to (decided by data inspection in week 4, exposed as the edition
  parameter either way); whether ffcsv carries quality flags as columns
  (week 1); UBA and Bundeswahlleiterin ToS follow-ups inherited from M1 (not
  AP2-blocking).

## 10. Explicitly out of scope for AP2

- New data sources beyond Destatis (application commitment: only after
  validated demand).
- Resampling/aggregation across frequencies, seasonal adjustment, any
  statistics beyond faithful re-keying and re-basing.
- A no-code or web interface; AP2 users are Python users.
- Scheduled live CI against any portal.
- Premium GENESIS features and bulk mirroring of whole statistics; we pull
  what a recipe names, politely.
- pystatis interop shims.

## References

- M1 chassis: `mloda_plugin_govdata/feature_groups/govdata/` and
  `docs/adding-a-reader.md` in this repo.
- mloda composition patterns: mloda-registry `docs/guides/`
  feature-group-patterns 02, 03, 04, 08, 11, 26, 27 (read before WP-E).
- GENESIS-Online RESTful/JSON API, Anwenderdokumentation v5.0 (06.05.2025):
  the binding contract for WP-A to WP-C.
- Eurostat NUTS/LAU correspondence tables (CC-BY-4.0); Destatis GV-ISys;
  BBSR Umsteigeschluessel (dl-de/by-2-0, attribution "Laufende
  Raumbeobachtung des BBSR", confirmed 2026-06-17).
- Private planning companion repo: research parts A to D, strategies, ADRs,
  learnings log (update as AP2 progresses).
