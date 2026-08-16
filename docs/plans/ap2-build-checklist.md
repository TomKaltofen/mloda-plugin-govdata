# AP2 build checklist

Companion to [ap2-destatis-harmonization.md](ap2-destatis-harmonization.md)
(the plan). The plan says what and why; this file is the tickable build order.
Tick items in the PR that lands them. If a slice moves, a checkpoint slips, or
a cut line is pulled, edit both files in the same PR.

Status: draft v2, 2026-08-16. v1 was reviewed by three independent advisors
(two Claude models, one Codex run) against the M1 code and mloda 0.10.0; the
findings are folded in below. Items marked "verified" were checked against the
installed code, not assumed.

## How to use

- One slice is one PR (or a short PR series) on the fork, opened against
  upstream `main` when green. Slice numbers are the build order, not the WP
  order; WP-D (mapper) is standalone and interleaves.
- Every PR: `tox` green, no live network in the default test run, no
  credentials in fixtures or snapshots, Conventional Commit, plan section
  reference in the PR body.
- `[ ]` open, `[x]` done, `[-]` cut or deferred (say where it went, one line).
- Hours per slice are the plan's WP hours split across slices. Where this
  checklist prices work the plan did not (join plumbing, week-0
  characterization, offline cache mode), it says so and the WP total moves.
  Checklist total: about 251 h against the plan's 245 h (WP-E carries the
  8 h of join plumbing).
- External items (GitHub issues, ADRs, planning-repo updates, funder
  updates) are ticked with a URL or commit id next to the box, so the tick
  is evidence, not a memory.

## Capacity assumption and weekly load

This order assumes about 38 h/week of implementation time from Aug 17 to
Sep 30 (about 31 working days after SciCAR), with WP-G's 20 h spread on top
(about 3 h/week). Below 30 h/week, pull cut line 1 at the start of week 3,
not at C2. Below 25 h/week, open the scope conversation with the funder
before the mid-September update (execution notes, section 1). Log hours
weekly so the C1 decision is made on data.

Load as ordered (slice hours only):

| Week | Slices | Hours | Note |
|------|--------|-------|------|
| 0 (Aug 14 to 16) | 0 | 8 | partial week |
| 1 (Aug 17 to 23) | 1, 2, 8 (week-1 part) | 57 | about 19 h over; see below |
| 2 (Aug 24 to 30) | 3, 4 | 40 | C1 |
| 3 (Aug 31 to Sep 6) | 5, 6, 7 | 38 | |
| 4 (Sep 7 to 13) | 8 (week-4 part) | 35 | |
| 5 (Sep 14 to 20) | 9 | 15 | three days, C2, about 8 h buffer |
| 6 (Sep 21 to 27) | 10, 11 | 38 | |
| Sep 28 to 30 | acceptance | 6 | |

Week 1 is the only week over budget. Decide in slice 0 which of these
applies: (a) week 1 runs long (about 57 h) and week 5's buffer absorbs
nothing; (b) slice 8's week-1 de-risking (10 h) moves to the start of week
4, accepting that the WP-D unknown is answered three weeks later; (c) cut
line 1 is pre-pulled and slice 7's join plumbing shrinks to a Destatis-only
join (saves about 4 h in week 3, not week 1). None of these is free; the
checklist does not pick for you.

## Standing rules (checked on every PR)

- [ ] `tox` (pytest, ruff format, ruff check, mypy strict, bandit) passes.
- [ ] Default `pytest` run does no network I/O (`live` and `genesis_live`
      deselected by `addopts`); `genesis_live` tests skip with a visible
      reason when credentials are absent (D8).
- [ ] No token, user, or password in code, fixtures, cache keys, metadata,
      recipes, logs, `repr` output, or test snapshots (WP-A redaction rule).
- [ ] Real payload fixtures ship with a `NOTICE` naming source, license, and
      attribution (D9).
- [ ] Tests live next to the module they test, mirroring
      `feature_groups/govdata/tests/` (so `feature_groups/destatis/tests/`,
      `harmonization/tests/`, `recipes/tests/`); each new tests package gets
      its own `conftest.py` with `fixtures_dir`.
- [ ] Silent wrong output is the only forbidden outcome (rulebook, section 6).

## Slice 0: week 0 spec analysis, pre-flight and characterization (Aug 14 to 16, live checks may spill into week 1, about 8 h)

Throwaway code only. Resolves plan section 9 week-0 questions and moves the
three unknowns that gate C1 (auth mechanism, ffcsv shape, table size) two
weeks earlier. Hours count toward WP-A. Order: step 0 is the spec analysis
(offline), then the paper work (needs the GENESIS web UI and the other
portals, not the webservice), and the live webservice checks come last, so a
degraded backend (Aug 16) blocks nothing else.

**Step 0: OpenAPI analysis (offline, about 1 h)**

- [ ] Assess the OpenAPI spec as a discovery and configuration aid. Spec:
      `https://genesis.destatis.de/genesisWS/rest/2020/GOJsonApi.json`
      (Swagger UI: `https://genesis.destatis.de/genesisWS/swagger-ui/index.html`),
      pinned 2026-08-16 in the planning repo (`planning/research/`, sha256
      `1a0dc57a...`). Found so far: 45 paths, credentials declared as
      `username` / `password` header parameters, every form parameter with
      its default (`data/tablefile` has `quality`, default `off`, absent from
      the PDF), 110 response schemas (`Status`, `Ident`, `TableMetadata`,
      `TablesCatalogue`, ...), but no parameter descriptions and no enums, so
      allowed values still come from the PDF. Decide and write into plan
      section 5: (a) slice 2 contract test that `GenesisClient` endpoint and
      parameter names match the spec; (b) D10 envelope models derived from
      `Status` / `Ident` / `Parameter` / `Object` / `Copyright`; (c) a
      user-facing `docs/destatis-options.md` (parameter, default from the
      spec, allowed values from the PDF, which `DestatisLocator` field it
      maps to) so users can discover options before configuring a
      FeatureGroup; (d) whether a typed discovery helper over
      `catalogue/tables`, `metadata/table`, `catalogue/qualitysigns` moves
      from stretch into slice 4 (about 8 h) or stays stretch.

**Paper work (web UI and other portals, no webservice needed, about 4 h)**

- [ ] Pin the three recipe tables: population by Kreis (12411 family), a
      Kreis-level labor-market or income indicator, population by Land.
      Check host (GENESIS-Online vs Regionalstatistik) for each in the web
      UI. Write the codes into plan section 5 WP-F and section 9.
- [ ] If any recipe table lives on Regionalstatistik: move that host into
      WP-A scope, add about 10 h, update the plan and the execution notes.
- [ ] Check Berlin in each pinned table: present as `11` (Land table) or
      `11000` (Kreis tables) with a real value, not a null marker. Berlin is
      the city-state case slice 8 tests and the Land row recipe 3 joins on.
      If a Kreis table lists city-states differently or not at all, record
      how (Hamburg `02000`, Bremen `04011` and `04012`) or pick another
      table. The week-0 table in `learnings/` gets a "Berlin present" column.
- [ ] Fetch the real full `kerg.csv` once and confirm which `gehört zu`
      value marks Land rows and which marks Bundesgebiet (D2 assumes `99`;
      the committed `kerg_sample.csv` has no Land rows, verified). Fix D2
      wording if wrong.
- [ ] Name the Gebietsstand change the U2 scenario will re-base across:
      confirm in GV-ISys that it is Kreis-level (not Gemeinde-level), confirm
      the BBSR Umsteigeschluessel cover that year pair, write old and new AGS
      into plan section 5 WP-E, and record one fallback candidate. Osterode
      am Harz into Göttingen (2016, 03156 into 03159) is a candidate; verify,
      do not assume.
- [ ] Make C2 reproducible on paper: for that change, write down the exact
      GENESIS table and selection (code, years, regional keys), the source
      and target Gebietsstand, the BBSR key file version and direction, and
      compute the expected re-based values for two or three cells by hand
      from the key file. This becomes the expected-value fixture in slice 9.
- [ ] Decide whether to pre-pull cut line 2 (annual-only period parsing).
      All six recipes and acceptance item 3 are annual, so this frees about
      5 h of slice 7 as banked buffer. Record the decision in the plan.
- [ ] Open one GitHub issue per WP (A to G) plus an M2 milestone on
      `mloda-ai/mloda-plugin-govdata` (the fork has issues disabled).
- [ ] Planning repo: milestones.md flips AP1 to done (residue listed) and AP2
      to in progress; funder-update dates recorded (execution notes section 2).

**Live webservice checks (last; run when the backend answers, before slice 2, about 3 h)**

- [ ] Run a live `helloworld/whoami`, then characterize
      `helloworld/logincheck` with token-only, user plus password, and both.
      One-off script, not committed; responses recorded redacted. Record the
      result and the exact auth mechanism observed in the planning repo
      (`learnings/`). 2026-08-16: mechanism confirmed against doc v5.1, the
      OpenAPI spec, and the echoed `Username` (headers); a successful
      `logincheck` ("Sie wurden erfolgreich an- und abgemeldet!") is still
      outstanding because the webservice backend returned "unerwarteter
      Systemfehler" all day (same result in the official Swagger UI).
- [ ] With the same script, run one real `data/tablefile` request per
      pinned table with the intended selection (`format=ffcsv`, years,
      `regionalvariable` and `regionalkey`). Record per table: HTTP status,
      envelope status block, zip member names and count, header line, row
      count, Berlin present, and whether the too-large envelope appears.
      Save the three payloads, redacted, for commit as fixtures in slice 2.
      Done state: a table in `learnings/` with those columns filled for all
      three.
- [ ] Merge the plan PR (#12) after review, with this checklist.

## Slice 1: reader seams and offline cache mode (WP-B, week 1, about 10 h)

Refactor only; M1 behavior unchanged. Everything a second locator type and a
POST reader need from the base class lands here.

- [ ] `reader.py`: parameterize the reader over its locator type
      (`BaseGovDataReader(ReadFile, Generic[LocatorT])` or a `Locator`
      Protocol) so `_coerce_locator`, `match_subclass_data_access`,
      `_read_table`, `_fetch`, and `_parse` are typed on `LocatorT`.
      `_unknown_features_message` uses a locator `describe()` instead of
      `dataset_id` / `distribution_url` (verified: today all three are typed
      on the concrete `GovDataLocator`, and an argument-narrowing override
      fails `mypy --strict` as a Liskov violation).
- [ ] Seam dataclasses defined first, in `core/provenance.py`: `Provenance`
      (source label, url or endpoint plus parameters, and the license and
      dataset metadata `ResolvedDistribution` carries today, verified in
      `core/discovery.py`, so nothing the recipes' compliance block needs is
      dropped) and `FetchedPayload` (`path`, `sha256`, `retrieved_at`,
      `provenance`). The sha256 is over the bytes stored in the cache (for
      Destatis: the raw zip; the extracted CSV hash is a second field if the
      recipes need it; decide and write it down here).
- [ ] `reader.py`: extract `_fetch(locator, client) -> FetchedPayload` out of
      `_read_table`; `_parse(path, locator, provenance, options)` replaces the
      `ResolvedDistribution` parameter. `ResolvedDistribution` stays exported.
- [ ] `core/discovery.py`: `ResolvedDistribution` maps into `Provenance`; the
      CKAN plus GET path stays the base implementation of `_fetch`.
- [ ] Update `GovDataReader._parse` (in `reader.py`), `bundeswahlleiterin.py`,
      `uba.py`; behavior unchanged (`population.py` has no `_parse`, verified).
- [ ] `core/cache.py`: `DownloadCache.get_or_download(url, *,
      revalidate=True)`; `revalidate=False` returns the stored body with no
      request and raises a network error naming the URL on a miss (verified:
      today every call issues a conditional GET, so there is no offline read).
      The meta file gains `retrieved_at` (verified: not stored today, so
      `FetchedPayload.retrieved_at` cannot be reconstructed on a hit); old
      meta files without it are treated as a miss.
- [ ] Tests: a throwaway second locator type plus a two-line reader subclass
      local to the test module; `mypy --strict` green; a `{"FakeReader":
      "x"}` option never yields a `GovDataLocator`; the fake `_fetch` override
      never calls `resolve_distribution` (respx asserts zero CKAN calls); a
      `revalidate=False` read makes zero HTTP calls.
- [ ] Backfill `NOTICE` for the M1 fixtures (`population_sample.csv`,
      `kerg_sample.csv`, `berlin_wahl_sample.csv`, `uba_measures.json`; none
      has one today, verified).
- [ ] `docs/adding-a-reader.md`: one paragraph on the locator type and the
      `_fetch` seam.
- [ ] Commit `refactor: locator-generic reader with fetch seam and offline
      cache read`.
- [ ] Planning repo: ADR 0002 (module layout and reader seams), status
      proposed.

## Slice 2: Destatis credentials, client, envelope (WP-A, week 1, about 37 h)

Package `mloda_plugin_govdata/feature_groups/destatis/` with `core/` and
`tests/`. WP-A total 45 h = slice 0 (8 h) + this slice.

- [ ] Verify against Anwenderdokumentation v5.1 (01.06.2026) and the week-0
      observation: endpoint names, POST form parameters, and the auth
      mechanism (credentials as `username` / `password` HTTP headers, token
      in `username` with empty `password`; body credentials are ignored and
      run as `GAST`). Record in ADR 0004.
- [ ] `core/auth.py`: `DestatisCredentials` (token, or user plus password;
      host-scoped). Resolution order: explicit option, then env
      (`GENESIS_TOKEN`, `GENESIS_USER`, `GENESIS_PASSWORD`, host-prefixed
      variants). Whitespace normalized. `__repr__` and `__str__` redact.
      `MissingCredentialsError` names the env vars, says registration is free
      and same-day, and gives the URL.
- [ ] Env-var names live in a tuple or frozenset, not in `*_TOKEN` or
      `*_PASSWORD` named constants and not as dict keys with string-literal
      values (verified: bandit B105 flags all three forms and `tox` runs
      bandit on the package); otherwise a scoped `# nosec B105` with a
      one-line reason.
- [ ] Credentials passed explicitly go to `Options.context`, never `group`
      (verified: `group` feeds `Options.__hash__` and any options dump);
      `DestatisLocator` carries no credential field. Test asserts no secret
      in `repr(credentials)`, `str(credentials)`, or `repr(options)`.
- [ ] `core/api.py`: `GenesisClient` over `govdata/core/client.build_client`.
      `post(endpoint, params)` form-encoded, `language` pinned per request.
      Auth failures are never retried (bypass `request_with_retry` on those).
- [ ] D7 lock, stated honestly: a `threading.Lock` serializes calls within
      one process only. First characterize how mloda's `THREADING` and
      `MULTIPROCESSING` modes reach `load_data` (which process, how many
      client instances). Then `GenesisClient` either refuses to run under
      `ParallelizationMode.MULTIPROCESSING` (raise with the reason) or takes
      an inter-process file lock; pick one, test both halves (two threads
      serialize; two processes never overlap or the second refuses), and
      correct the D7 wording in the plan in the same PR.
- [ ] `core/envelope.py`: pydantic model for the application status block
      inside HTTP 200 bodies (D10). Map to typed exceptions:
      `GenesisAuthError`, `GenesisUnknownTable`, `GenesisEmptySelection`,
      `GenesisResultTooLarge`, `GenesisJobAccepted`, `GenesisMaintenance`
      (HTML body), `GenesisUnknownEnvelope` (raw status block quoted).
- [ ] Fixture capture tooling at `scripts/capture_genesis_fixtures.py` (repo
      root, not shipped): records real responses, redacts credentials from
      request and response (including the echoed `Username` field), writes
      the `NOTICE`. One test asserts redaction on a synthetic payload
      containing the token in original, upper-, and lower-cased form and the
      password URL-encoded (week 0 leaked a case-flipped echo this way).
- [ ] Fixtures under `feature_groups/destatis/tests/fixtures/`: `whoami`,
      `logincheck` ok and bad, one envelope per mapped error (bad
      credentials, unknown table, empty selection, too large, job accepted),
      a maintenance HTML page, and the three redacted week-0 tablefile
      payloads. `NOTICE` present. `tests/conftest.py` with `fixtures_dir`.
- [ ] Live-test gating scoped to Destatis: a second marker `genesis_live`
      registered in `pyproject.toml` next to `live` (and added to `addopts`
      deselection); Destatis live tests carry both. Repo-root `conftest.py`
      skips `genesis_live` tests when `GENESIS_TOKEN` (or user plus password)
      is absent, reason in the skip message. The plain `live` marker keeps
      covering the M1 GovData, election, and UBA live tests, which need no
      credentials and must not be skipped by this hook (verified: no root
      conftest exists today; the only one is
      `feature_groups/govdata/tests/conftest.py`).
- [ ] `docs/credentials.md` created here (env names, registration URL,
      dual-path explanation); slice 5 adds the too-large paragraph, slice 12
      polishes.
- [ ] Tests (respx): each auth path, each envelope mapping, no retry on auth
      failure, the lock serializes concurrent threads, `language` present in
      every request body, credentials absent from any logged or raised text.
- [ ] Live smoke (`live` and `genesis_live`): `whoami` plus `logincheck`.
- [ ] Commit series `feat(destatis): credentials and client`,
      `feat(destatis): status envelope mapping`, `test(destatis): fixtures`.

## Slice 3: parameter-keyed POST cache (WP-B, week 2, about 8 h)

- [ ] `destatis/core/cache.py`: `ParameterCache`, sibling of `DownloadCache`
      (do not extend it). Key: sha256 over canonical JSON of host, endpoint,
      normalized parameters (sorted region lists, integer years, stripped
      strings); credentials excluded before keying. Meta: parameters,
      `retrieved_at`, payload sha256, data file. Same `cache_dir` as the GET
      cache, key prefix `post-` so nothing collides.
- [ ] Freshness (D6): cache hit wins with no request; `refresh=True`
      refetches; a hit older than 30 days logs a warning naming the table and
      the age. No TTL. Same offline-first semantics as the GET cache's
      `revalidate=False` (slice 1), so D6 is symmetric across both caches.
- [ ] Tests: key stable under parameter reordering and list order; changes
      when a parameter changes; token or password in the params never reaches
      the key or the meta; refresh bypasses; staleness warning fires (inject
      the clock); corrupted entry re-downloads; a hit makes zero HTTP calls.
- [ ] Commit `feat(destatis): parameter-keyed POST cache`.
- [ ] Planning repo: ADR 0003 (cache), status proposed.

## Slice 4: tablefile, ffcsv parser, locator, reader (WP-B, week 2, about 32 h)

Checkpoint C1 target (Aug 30). Designed against the three real week-0
payloads, not a guess.

- [ ] `core/api.py`: `tablefile(...)` with `name`, `startyear`, `endyear`,
      `regionalvariable`, `regionalkey`, `classifyingvariable1..5`,
      `classifyingkey1..5`, `format=ffcsv`, `language`, `compress` (empty
      rows and columns suppression, not zip), `transpose`, `stand`,
      `quality` (default `off`; characterize `on` against one fixture, it is
      the quality-flag switch); envelope and HTTP status inspected before any
      parsing.
- [ ] Zip handling from the week-0 characterization: reject empty archives
      and unexpected member sets; enforce a decompressed-size cap; the CSV
      member is written into the cache entry.
- [ ] ffcsv shape contract written down from the three payloads: fixed
      prefix columns, N repeated variable blocks
      (`1_variable_attribute_code`, `2_...`), value and quality columns. The
      layout guard asserts the shape (block structure, no duplicates, all
      declared blocks present), not a literal name list, because width grows
      with the number of classifying variables. Test: the guard passes all
      three fixtures and raises on a hand-edited fourth with a dropped block.
- [ ] Declared column schema per fixture, recorded before the parser is
      written: required columns and optional columns (quality flags) with
      their Arrow types, following the M1 rule that parsing needs explicit
      types (`parse.py` `_typed_table`, verified). Policy: optional columns
      are read when declared and absent otherwise; undeclared columns raise
      (this is how "quality flags if present" and "unknown columns raise"
      coexist).
- [ ] `destatis/core/parse.py`: `parse_ffcsv_bytes(data, schema)` and path
      wrapper. Reuse `govdata/core/parse.detect_encoding`, `_clean_number`,
      `ZERO_MARKERS`, `NULL_MARKERS` (import, do not copy). `time` column
      parsed through the period model (until slice 7 lands, annual only as
      `int64` year with a TODO to the period model). A cell that cannot be
      typed raises with the offending cell and column.
- [ ] `destatis/locator.py`: `DestatisLocator` (D10 validation): table code
      (`12411-0015` style, validated), optional region and classifying
      selection, start and end year, `host` (GENESIS-Online default, D5),
      `language`, `format` pinned to `ffcsv`. Frozen (frozen dataclass with
      pydantic validation, or `ConfigDict(frozen=True)`) so it hashes
      natively inside `Options.group` like `GovDataLocator` does. `from_string`
      accepts a bare table code; `coerce` accepts a `DestatisLocator`, a
      string, or a plain dict (the JSON-native form recipes need, slice 6);
      `to_dict` round-trips it.
- [ ] `destatis/reader.py`: `DestatisReader(BaseGovDataReader[DestatisLocator])`
      with `match_subclass_data_access` and `_coerce_locator` on the Destatis
      locator, `_fetch` (POST through `ParameterCache`), `_parse`, `suffix`,
      `peek`. Tests: `{"DestatisReader": "12411-0015"}` never produces a
      `GovDataLocator` and never touches CKAN; class-key, string, and dict
      locators all reach `_fetch` through `mloda.run_all`;
      `DestatisReader.is_final_reader()` is `True` (mirrors the existing
      assertion in `govdata/tests/test_reader.py`).
- [ ] `peek` without credentials: `_fetch` computes the cache key and returns
      a hit before resolving credentials. Test: all `GENESIS_*` unset,
      pre-populated cache, `peek` succeeds with zero HTTP calls.
- [ ] Root FeatureGroup: decide whether `DestatisReader` hangs off
      `GovDataFeature` (via `BaseGovDataReader`) or gets its own root
      FeatureGroup; either way `test_resolves_without_explicit_compute_framework`
      (the M1 collision regression) stays green and the join in slice 7 has
      a discriminator to key on.
- [ ] Export from `feature_groups/destatis/__init__.py` (mirror
      `feature_groups/govdata/__init__.py`; the root `__init__.py` files are
      empty, verified). Test in a fresh subprocess: import only the
      documented Destatis surface, run `mloda.run_all` over a fixture, and
      assert the plan resolves to the chosen root FeatureGroup, so
      registration does not depend on an unrelated import.
- [ ] Fixtures: the three week-0 ffcsv zips plus an empty-result payload.
      `NOTICE` present.
- [ ] Tests: parser pinned to fixtures; zero-vs-missing (`-` is zero, `.`
      `...` `/` `x` `()` are null) per fixture; decimal comma and thousands
      dot; int64 counts never via float; utf-8, BOM, and cp1252 variants;
      empty result yields the declared schema and `peek` lists columns;
      duplicate or extra columns raise; reader end to end via
      `mloda.run_all` with respx (fixture zip served); unknown feature error
      names available columns.
- [ ] Live smoke (`live` and `genesis_live`): one tiny table via
      `mloda.run_all`.
- [ ] README: Destatis quickstart snippet (credentials via env, one table).
- [ ] Commit series `feat(destatis): tablefile request and zip handling`,
      `feat(destatis): ffcsv parser`, `feat(destatis): locator and reader`.
- [ ] **C1 (Aug 30):** a real GENESIS table arrives as a typed Arrow table via
      `mloda.run_all` from a clean cache. Result written into the plan and
      the biweekly update. If red: slices 5, 6, 10, 11 wait; slice 8 continues.

## Slice 5: result-too-large detection (WP-C, week 3, about 8 h)

- [ ] The envelope-to-`GenesisResultTooLarge` mapping already exists from
      slice 2; this slice owns the actionable message: why the password path
      is needed, how to shrink the selection (years, regions, classifying
      keys), and how to fetch manually (URL and steps). Never a truncated
      table.
- [ ] Test with the recorded envelope fixture; message content asserted.
- [ ] Docs: the too-large paragraph in `docs/credentials.md` (created in
      slice 2).
- [ ] `[-]` Full job path (`catalogue/jobs`, `data/resultfile`,
      `profile/removeresult`): stretch, only after acceptance is green.
- [ ] Commit `feat(destatis): actionable error for oversized results`.

## Slice 6: recipe format and writer (WP-F part 1, week 3, about 12 h)

- [ ] Build on `mloda.user.load_features_from_config(config_str, format="json")`
      (verified in mloda 0.10.0): takes a JSON string (not a path), returns
      `list[Feature | str]`, and requires a JSON array of feature names or
      objects with `name`, `options` (or `group_options` plus
      `context_options`), `in_features`, `feature_group` (class-name string).
      Any other key inside a feature item raises `TypeError` (verified:
      `FeatureConfig(**item)`), and a top-level object raises "must be a JSON
      array".
- [ ] `recipes/model.py`: the recipe file is therefore a JSON object
      `{"features": [...], "links": [...], "compliance": {...}}`; `features`
      is the mloda array verbatim and is passed as `json.dumps(recipe.features)`
      to the loader. `compliance` (D10 pydantic): license id, attribution
      string, dataset URI, retrieval timestamp, payload sha256, modification
      markers, required credential env names. Credential-looking values are
      rejected by the model.
- [ ] Option values inside `features` are JSON primitives only: reader
      locators go in as strings or dicts (`DestatisLocator.coerce(dict)`,
      slice 4). The writer only round-trips the JSON-safe subset of options
      this plugin produces (slugs, URLs, table codes, years, region lists,
      reader class-name keys); it is not a general `Options` serializer.
- [ ] `links` block: `load_recipe` turns it into `Link` objects (`Link.inner`
      with `JoinSpec`, `Index`, and `left_discriminator` /
      `right_discriminator`; verified exported from `mloda.user`), since the
      feature loader cannot express joins. Empty list allowed.
- [ ] `recipes/writer.py`: Feature list plus links plus compliance to recipe
      JSON; `load_recipe(path) -> LoadedRecipe` with `features:
      list[Feature | str]` (the loader's real return type, verified; not
      every `Feature` attribute survives the config model, so the supported
      round-trip subset is documented), `links: list[Link]`, `compliance`.
      It imports the plugin's feature-group modules first so a fresh process
      resolves them. Test: the compliance and links blocks are stripped
      before the feature JSON reaches mloda.
- [ ] Recipe file location decided together with the reference-data decision
      in slice 8: shipped as package data
      (`mloda_plugin_govdata/recipes/files/*.json` with
      `[tool.setuptools.package-data]`; verified: no package-data or
      MANIFEST.in exists today, so non-`.py` files are not reliably in the
      wheel) or repo-root `recipes/` outside the wheel. If shipped: a test
      builds the wheel and asserts the JSON files are inside.
- [ ] Tests: round trip; a recipe carrying a token-like value fails
      validation; a recipe with a mloda-unknown key inside a feature item
      fails at load with a clear message; a recipe over a fixture runs
      through `mloda.run_all` in a fresh subprocess.
- [ ] Commit `feat(recipes): recipe model, writer, loader`.

## Slice 7: period model and Land-level join plumbing (WP-E part 1, week 3, about 18 h)

Period model 10 h (plan). Join plumbing about 8 h, not priced in the plan;
it is what acceptance item 3 and recipe 3 stand on, so it is built and
tested here, three weeks before it is needed.

- [ ] Characterize each source's temporal semantics before coding:
      Destatis annual (reference date per table, often 31 Dec); kerg is an
      election snapshot with no time column at all (verified: the header is
      `Nr;Gebiet;gehört zu;Gewählt ...`), so the election date comes from
      the locator or recipe, not the file; UBA `date_start` is an ISO string
      per hour. Write the Arrow representation down: `period_start`
      (date32) plus `frequency` (string) columns.
- [ ] `mloda_plugin_govdata/harmonization/__init__.py` (pure Python, no mloda
      import) and `harmonization/period.py`: `Period(start: date, freq)` with
      `freq` in `{year, quarter, month}`; `parse_genesis_time(label)` for the
      labels present in the chosen tables (years first); `from_snapshot(date,
      freq)` for the election date; parser for UBA `date_start`.
- [ ] Snapshot-to-annual join policy, decided and documented: which Destatis
      reference year an election on date D joins to (for example the year
      containing D, or the last 31 Dec before D). One policy, stated in the
      recipe notes and the README, tested end to end on fixtures. No silent
      default.
- [ ] `assert_same_frequency(a, b)` raises with resampling guidance on
      mismatch; no implicit aggregation.
- [ ] Hypothesis: period round-trip, unknown label raises with the label.
- [ ] Wire the ffcsv `time` column to the period model (replaces the slice 4
      TODO).
- [ ] `[-]` Quarter and month parsing: dropped if cut line 2 was pre-pulled
      in slice 0, else the first candidate at C2.
- [ ] Join plumbing (verified against mloda 0.10: `Link.inner_on` reads
      `index_columns()`, which `GovDataFeature` does not define; a
      `DestatisReader` feature and a `BundeswahlleiterinReader` feature both
      resolve to `GovDataFeature`, so discriminators are mandatory):
      `index_columns()` on the joining feature group(s) returning the Land
      key; `Link.inner(...)` with `left_discriminator` / `right_discriminator`
      keyed on the reader option; the root-FeatureGroup decision from slice 4
      applied. Test: `run_all(features, links=...)` over fixtures returns one
      joined table with 16 Land rows (Destatis fixture on the left, a kerg
      fixture with Land rows on the right).
- [ ] Commit series `feat(harmonization): period model`,
      `feat(govdata): Land-level join plumbing`.

## Slice 8: AGS-to-NUTS mapper (WP-D, weeks 1 and 4, about 45 h)

Standalone module, usable without mloda. Week 1 (about 10 h): extracts,
hand-verified mapping, and the packaging decision. Week 4 (about 35 h):
loaders, key model, edition model, mapping.

- [ ] Week 1: capture one small redistributable extract per reference source
      (Eurostat NUTS correspondence, LAU-to-NUTS, GV-ISys, BBSR
      Umsteigeschluessel Kreise) with URL and sha256 pinned; `NOTICE` with the
      Destatis, Eurostat, and BBSR long-form attributions.
- [ ] Week 1: map five hand-picked AGS keys (one city-state, the merged
      Kreis from slice 0, one Gemeindefreies Gebiet, two ordinary Kreise) to
      NUTS-3 by hand from the captured extracts and paste the table into ADR
      0006. If no direct 5-digit correspondence exists in the sources (LAU is
      Gemeinde-level), the derivation is designed here, not in week 4.
- [ ] Week 1: packaged data vs runtime fetch decided (shared with slice 6).
      If packaged: `[tool.setuptools.package-data]` (and MANIFEST.in) plus a
      wheel-content test. If runtime fetch: the default edition is called
      "latest cached", and an offline call with an empty cache raises with
      the fetch instruction instead of silently using a fixture edition.
- [ ] Add `openpyxl` to dependencies (D11): edit `pyproject.toml`, refresh
      `uv.lock` (`uv sync --all-extras`), commit both; respects
      `exclude-newer`; `tox` green and `tox -e security` (pip-audit) clean as
      an additional check. Raise `timeout-minutes` in
      `.github/workflows/test.yml` in the same PR (verified: 2 minutes today
      for the whole tox run on a five-version matrix).
- [ ] `harmonization/keys.py`: AGS 2, 5, 8 digit and 12-digit ARS detection;
      keys are strings with leading zeros end to end; Excel-mangled integer
      keys repaired only when unambiguous by level and length, else raise;
      mixed levels in one input raise.
- [ ] `harmonization/reference/`: one loader per source (xlsx via openpyxl,
      GV100 fixed-width ASCII), each reading through the GET `DownloadCache`
      with `revalidate=False` by default (offline first, explicit refresh),
      pinned by URL plus sha256, with the fixture extract for tests.
- [ ] `harmonization/edition.py`: `Edition(gebietsstand, nuts_version)` plus
      the reference-data identity it was built from (source, URL, sha256,
      covered year range); default per the week-1 decision (read from the
      shipped or cached tables, not a constant).
- [ ] `harmonization/nuts.py`: exact API written down before coding:
      `map_ags_to_nuts(keys, *, edition, data_year=None,
      on_unmatched="raise" | "drop" | "flag") -> MappingResult` with
      `matched` (key, nuts1, nuts2, nuts3, nuts_version), `unmatched`
      (structured report), `edition`. `data_year` drives the warning when it
      diverges from the edition year and the error (with the covered range)
      when it falls outside key coverage; without it neither check runs and
      the result says so. Joining results across NUTS versions raises.
- [ ] Tests: hypothesis on string-key preservation and level detection;
      city-states (Berlin, Hamburg, Bremen and Bremerhaven) consistent;
      Gemeindefreie Gebiete appear in the unmatched report; the slice-0
      Kreis merger mapped in both editions; edition mismatch raises; the
      "partially validated" LAU table caveat documented in the loader
      docstring; the five hand-mapped keys from ADR 0006 pinned as a test.
- [ ] `[-]` Gemeinde (8-digit) and ARS mapping: stretch (D4); string keys keep
      the door open.
- [ ] Commit series `feat(harmonization): key model`,
      `feat(harmonization): reference loaders`, `feat(harmonization): AGS to
      NUTS mapping`.
- [ ] Planning repo: ADR 0006 (reference data policy, closes the BBSR license
      ADR action), status proposed.

## Slice 9: re-basing across Gebietsstand (WP-E part 2, week 5, about 15 h)

Checkpoint C2 target (Sep 20). Week 5 is three working days (SciCAR).

- [ ] `harmonization/rebase.py`: apply BBSR proportional keys onto a target
      Gebietsstand; direction and key edition explicit arguments; documented
      rounding; share-sum check with tolerance (renormalize inside, raise
      beyond); every re-based value carries a flag column; observed values
      never replaced in place; census breaks (2011, 2022) noted in output
      metadata, not smoothed.
- [ ] Expected-value fixture from slice 0: the hand-computed re-based cells
      for the named series, key file version, and direction, committed under
      `harmonization/tests/fixtures/` with the `NOTICE`.
- [ ] Tests: hypothesis share-sum property; direction asserted from the key
      file's own metadata in a fixture test; duplicated pairs and zero-share
      rows detected; the named multi-year Kreis series re-based across the
      slice-0 Gebietsstand change matches the expected-value fixture cell
      for cell, with flag column and edition metadata asserted.
- [ ] Commit `feat(harmonization): re-basing with BBSR keys`.
- [ ] Planning repo: ADR 0005 (harmonization as data plus flags), status
      proposed.
- [ ] **C2 (Sep 20):** that named test is green on `main` (re-based
      multi-year Kreis series, flagged, edition-pinned, exact values). If
      red: pull cut line 3 (slice 10 shrinks to module plus notebook; see
      the slice 11 note on what that does to recipes 1 and 3).

## Slice 10: harmonization FeatureGroups (WP-E part 3, week 6, about 15 h)

- [ ] Read mloda-registry feature-group-pattern guides 02, 03, 04, 08, 11,
      26, 27 before writing code. Done state: the PR body names which guide
      each design choice follows (naming, `input_features`, required-context
      forwarding).
- [ ] `feature_groups/harmonization/`: derived FeatureGroups over reader
      outputs: AGS-to-NUTS, re-base, period alignment. D1 naming
      (`destatis__bevoelkerung__kreise`, ASCII rule). Written down before
      coding, per the guides: the FeatureGroup base and parser mixin used,
      what `input_features()` returns (the child `Feature` objects with the
      required options such as edition and locator attached), how the
      `in_features` option is used, and how context is propagated
      (`Options` forwarding). Any required context option travels with the
      child features so chained requests resolve.
- [ ] Tests: `mloda.run_all` over fixtures for each FeatureGroup; one test
      runs a chained request with edition and locator options in a fresh
      subprocess.
- [ ] `[-]` Cut line 3: pure module plus a worked notebook example if C2 is
      red or week 6 is short.
- [ ] Commit `feat(harmonization): mloda feature groups`.
- [ ] Planning repo: ADR 0008 (feature surface D1, join level D2), status
      proposed.

## Slice 11: six recipes (WP-F part 2, week 6, about 23 h)

- [ ] `harmonization/land_codes.py`: the 16-row Land name to AGS-2 constant
      (D2), with a test against the kerg Land rows using the marker verified
      in slice 0.
- [ ] Recipe 1: population by Kreis over time (12411 family), the U2
      re-basing scenario; runs against fixture; compliance block filled.
- [ ] Recipe 2: Kreis-level labor-market or income indicator, the U1
      rate-with-denominator scenario; zero-vs-missing test.
- [ ] Recipe 3: Destatis population by Land joined with Bundestagswahl results
      by Land (D2) through the slice 7 `links` block; the flagship
      integration test and the Demo Day story.
- [ ] Retrofit 1: population (M1) as a recipe file.
- [ ] Retrofit 2: elections (M1) as a recipe file.
- [ ] Retrofit 3: UBA (M1) as a recipe file.
- [ ] Every recipe: license id, attribution, dataset URI, retrieval timestamp,
      payload sha256, modification markers, credential env names; one
      zero-vs-missing test; one `mloda.run_all` fixture test.
- [ ] If cut line 3 was pulled: recipes 1 and 3 keep their raw-pull features
      as JSON recipes; the harmonized or joined step moves to the notebook,
      and acceptance items 2 and 3 are carried by the module tests plus the
      slice 7 join test rather than by a recipe. Say so in the recipe notes.
- [ ] `[-]` Cut line 1: recipe 3 becomes a Destatis-only two-table join.
- [ ] `[-]` Cut line 4: retrofits shrink to one worked file plus a template.
- [ ] Commit series `feat(recipes): destatis recipes`, `feat(recipes): M1
      retrofits`.

## Slice 12: docs, demo, handoff (WP-G, woven through, about 20 h)

- [ ] README: Destatis section (auth, one table, one harmonized example,
      recipes).
- [ ] `docs/adding-a-reader.md`: the Destatis path (POST reader over the
      fetch seam).
- [ ] `docs/credentials.md`: env names, registration URL, dual-path
      explanation, too-large guidance.
- [ ] `demos/govdata_demo.py`: Destatis chapter (recipe 3 as the story).
- [ ] `pyproject.toml` description: "GENESIS API v3" becomes "GENESIS API
      v5.0" (or drop the version).
- [ ] Planning repo: ADRs 0002 (slice 1), 0003 (slice 3), 0004 (slice 2),
      0005 (slice 9), 0006 (slice 8), 0007 (pystatis considered and not
      adopted, written from execution notes section 5, no code slice), 0008
      (slice 10) flipped to accepted as their PRs merge; learnings filed the
      day a surprise appears; milestones.md updated; hours logged weekly
      (execution notes section 1).
- [ ] Manual live smoke run before each biweekly funder update; result stated
      in the update (D8).

## Acceptance walkthrough (Sep 28 to 30)

Plan section 1, checked one by one on `main` from a clean cache. Each item
names the cut line that changes its wording, so the walkthrough does not
have to reconstruct that under deadline pressure.

- [ ] 1. `DestatisReader` pulls two real GENESIS tables end to end into typed
      Arrow tables via `mloda.run_all` (same call shape as M1 readers). No
      cut line touches this.
- [ ] 2. 5-digit AGS to NUTS-1/2/3 with explicit edition; one real multi-year
      Kreis series re-based across a Gebietsstand change with BBSR keys.
      Cut line 3: carried by the module tests, not a FeatureGroup.
- [ ] 3. Typed period representation joins Destatis annual data with one M1
      source at Land level. Cut line 1: reads "joins two Destatis tables at
      Land level; the cross-portal claim moves to AP3". Cut line 3: carried
      by the slice 7 join test, not a recipe.
- [ ] 4. Six recipe files with all compliance fields. Cut line 4: reads "four
      recipe files plus a documented retrofit template".
- [ ] 5. `tox` green, no live network by default, README and demo updated.
      No cut line touches this.
- [ ] Plan status flips to "M2 reached" (or lists the honest residue);
      milestones.md and the funder update D say the same.

## Cut lines (pull in this order, tick when pulled, name the slice)

- [ ] 1. Cross-portal recipe becomes Destatis-only (slice 11).
- [ ] 2. Quarter and month period parsing drop (slice 7). May be pre-pulled
      in slice 0 as banked buffer.
- [ ] 3. Harmonization FeatureGroups drop to module plus notebook (slice 10;
      recipes 1 and 3 degrade as described in slice 11).
- [ ] 4. Retrofits shrink to one plus template (slice 11).

Never cut: compliance fields, zero-vs-missing tests, flags on harmonized
values, `tox` green.

## Stretch (only after acceptance is green)

- [ ] Full job path (submit, poll, download, remove), about 20 h.
- [ ] Gemeinde-level mapping, about 15 h.
- [ ] Regionalstatistik host, about 10 h (moves into scope in slice 0 if a
      recipe table needs it).
- [ ] Discovery helper, about 8 h.
