# AP2 build checklist

Companion to [ap2-destatis-harmonization.md](ap2-destatis-harmonization.md)
(the plan). The plan says what and why; this file is the tickable build order.
Tick items in the PR that lands them. If a slice moves, a checkpoint slips, or
a cut line is pulled, edit both files in the same PR.

Status: draft v2.4, 2026-08-16 (slice 3 ticked, pulled forward from week 2; slice 2 ticked, D7 wording corrected in the plan). v1 was reviewed by three independent advisors
(two Claude models, one Codex run) against the M1 code and mloda 0.10.0; the
findings are folded in below. Slice 0 step 0 (OpenAPI assessment) was done
2026-08-16, reviewed by one Claude Sonnet run and one Codex run against the
pinned spec, and folded into slices 0, 2, 4, 5, 12 and the stretch list.
Slice 0 paper work was done 2026-08-16 (tables and hosts pinned, U2 change
named, C2 on paper, kerg markers, ffcsv shape from Destatis' example files;
four learnings in the planning repo) and folded into slices 2, 4, 7, 8, 9,
11, the cut lines and the stretch list. Items marked "verified" were checked
against the installed code or the real data, not assumed.

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
  8 h of join plumbing). The step-0 outcomes add no hours: the contract
  test replaces the manual endpoint check inside slice 2's 37 h, the
  options doc is 2 h of WP-G's 20 h (less polish later), and the extra
  fixtures ride on the capture script. The week-0 paper work moves the
  Regionalstatistik host into WP-A scope (the plan's about 10 h); by owner
  decision (2026-08-16, "ignore hours, finish slice 0") this is recorded, not
  re-budgeted, and the week-1 overload options below stay unpicked.
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
checklist does not pick for you. Slice 0 outcome (2026-08-16): the owner
deferred the pick ("ignore hours"); the three options stand.

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

- [x] 2026-08-16, plan section 5 WP-A. Assessed the pinned spec
      (`https://genesis.destatis.de/genesisWS/rest/2020/GOJsonApi.json`,
      Swagger UI `.../genesisWS/swagger-ui/index.html`, planning repo
      `planning/research/genesis-openapi-GOJsonApi-2026-08-16.json`, sha256
      `1a0dc57a...`) against the PDF v5.1 text: 45 paths, 46 operations (44
      POST, 2 GET: `whoami` and `catalogue/qualitysigns`), `username` /
      `password` as header parameters on 43 operations (none on `whoami`
      and the two `qualitysigns` operations; PDF 2.4.6 agrees, PDF 2.1.3
      says only `whoami` is exempt, so it is a live check), 110 component
      schemas, every request input a string with no description, enum, or
      `required`, every response `default` (no HTTP status codes), the four
      `*file` operations typed `application/octet-stream` with a generic
      `Response` object, `Parameter` declaring `username` and `password` on
      all 33 `*Parameter` schemas (masked in the PDF examples, the observed
      `logincheck` echo is real), `data/tablefile` carrying `quality`
      (default `off`, absent from the PDF), the path spelled
      `profile/removeResult` (spec and PDF 2.7.2 URL), and the
      `qualitysigns` list (`0 - ... / . x () p r s`, PDF 2.4.6) being the
      machine-readable form of M1's marker sets. Decisions: (a) contract
      test in slice 2 (about 2 h, replaces the manual endpoint check);
      (b) envelope models from `Status` / `Ident`, one model per reply
      shape, `Object` / `List` optional, `Parameter` credentials stripped,
      `Type` case-insensitive; (c) `docs/destatis-options.md` in slice 4
      (about 2 h under WP-G); (d) discovery helper stays stretch (D5),
      slice 2 captures `metadata/table` per pinned table and one
      `qualitysigns` reply instead. Corrections landed in slices 2, 4, 5,
      12 and the stretch list below.

**Paper work (web UI and other portals, no webservice needed, about 4 h)**

Done 2026-08-16 through the web UIs' own JSON backends
(`genesis.destatis.de/genesis/api/rest`, `www.regionalstatistik.de/gngServer/api/rest`,
unauthenticated, read-only), the full `kerg.csv`, the BBSR and GV-ISys files,
and Destatis' ffcsv example zip. Evidence: planning repo
`learnings/2026-08-16-week0-recipe-tables-hosts-and-kerg-markers.md`,
`...-genesis-dash-marker-means-not-applicable-for-dissolved-kreise.md`,
`...-bbsr-kreis-umsteigeschluessel-shape-defect-and-c2-cells.md`,
`...-ffcsv-new-format-shape-from-official-examples.md`.

- [x] 2026-08-16. Pinned: (1) `12411-0015` Bevölkerung: Kreise, Stichtag
      (GENESIS-Online, `KREISE`, `STAG` 1995 to 2025); (2) `13211-02-05-4`
      Arbeitslose und Arbeitslosenquoten, Jahresdurchschnitt ab 2009, Kreise
      (Regionalstatistik, `KREISE`, `JAHR` 2001 to 2025, contents `ERWP06`
      count and `ERWP10` rate); (3) `12411-0010` Bevölkerung: Bundesländer,
      Stichtag (GENESIS-Online, `DLAND`, `STAG` 1958 to 2025). Written into
      plan section 5 WP-F and section 9. GENESIS-Online has 31 Kreis-level
      tables and no labor-market or income one; fallback for (2) if the
      Regionalstatistik path fails: `12521-0040` over `12411-0015`.
- [x] 2026-08-16. Recipe 2 lives on Regionalstatistik: host moved into WP-A
      scope (plan D5, WP-A; slice 2 items below). Hours recorded (about 10 h
      in the plan's terms), not re-budgeted (owner decision). Owner action:
      register a Regionalstatistik webservice account (free, own token,
      IT.NRW; the GENESIS-Online token is not valid there). Its spec is
      pinned in the planning repo (`genesis-openapi-regionalstatistik-GOJsonApi-2026-08-16.json`,
      sha256 `a9ce7944...`); request side identical for our endpoints, `servers`
      is lower-case `/genesisws`.
- [x] 2026-08-16. Berlin present with real values in all three: `11000` in
      `12411-0015` (2015: 3,520,031) and in `13211-02-05-4` (rate men 2024:
      10.0), `11` in `12411-0010`. Hamburg `02000`, Bremen `04011`,
      Bremerhaven `04012` present in the Kreis tables. "Berlin present"
      column is in the week-0 learning table.
- [x] 2026-08-16. Full btw25 `kerg.csv` (163,828 bytes, sha256
      `31ab2739...`): 299 Wahlkreis rows, 16 Land rows with `gehört zu = 99`
      whose `Nr` is the Land AGS-2 (`11;Berlin;99`), one Bundesgebiet row
      `99;Bundesgebiet;` with empty `gehört zu`, 16 `;` separator rows. D2
      holds; join key is `Nr` = `DLAND` (plan D2 reworded). Correction: the
      committed `kerg_sample.csv` does contain one Land row
      (`01;Schleswig-Holstein;99`, line 12), so the earlier "no Land rows,
      verified" note here was wrong; slice 7's join test can start from the
      existing fixture and only needs more Land rows.
- [x] 2026-08-16. Named: Landkreis Göttingen 2016, `03152` + `03156` into
      `03159`, 01.11.2016; GV-ISys `Namens-Grenz-Aenderung/2016.xlsx` (sha256
      `301a0b72...`) change `03/2016/0006-R`, rows of type `Kreis`, so it is
      Kreis-level; BBSR `ref-kreise-1990-2024.xlsx` (sha256 `68c4d001...`)
      sheet `2015-2016` maps both to `03159` with share 1. Fallback:
      Eisenach `16056` into Wartburgkreis `16063`, 01.07.2021 (sheet
      `2020-2021`). Fractional-share case: Cochem-Zell `07135` in sheet
      `2013-2014` (0.9828486 population share stays, 0.0171514 to `07140`).
      Written into plan section 5 WP-E.
- [x] 2026-08-16. C2 on paper: `12411-0015`, `regionalvariable=KREISE`,
      `regionalkey=03152,03156,03159`, `startyear=2013`, `endyear=2017`,
      contents `BEVSTD`; source Gebietsstand of each Stichtag, target
      31.12.2016; BBSR sheet `2015-2016`, population-proportional column,
      direction 2015 to 2016. Expected `03159`: 322,616 (2013), 324,013
      (2014), 329,538 (2015), observed 327,065 (2016), 328,036 (2017).
      Fractional check: `07135` 2013 = 63,202 becomes 62,118, `07140` 100,770
      becomes 101,854. Full table in the BBSR learning; slice 9 fixture.
- [x] 2026-08-16. Cut line 2 pre-pulled: every pinned table is annual (`STAG`
      31.12. or `JAHR`); recorded in the plan (section 5 WP-E, cut lines) and
      below (slice 7, cut lines). Reversible at C1.
- [-] GitHub issues per WP and the M2 milestone on
      `mloda-ai/mloda-plugin-govdata`: deferred 2026-08-16 (owner: work only
      on the fork for now; execution notes section 9 keeps the item).
- [x] 2026-08-16. Planning repo: milestones.md flips AP1 to done (residue
      listed) and AP2 to in progress; execution notes section 6a records the
      slice-0 outcomes.
- [ ] Planning repo: funder-update dates recorded (execution notes section 2;
      needs the Zulip history).

Findings that changed later slices (all 2026-08-16): GENESIS writes `-` for
a Kreis outside its Gebietsstand validity, on both hosts (slices 4, 8, 9,
11); the current ffcsv is long format with English headers and `value_unit`
in the row key, known from Destatis' example zip (slice 4); the BBSR Kreis
file has year-pair sheets, Excel-mangled 8-digit keys, and stale fractions on
two sheets (slices 8, 9); Regionalstatistik is a second host with its own
registration (slice 2, stretch list).

**Live webservice checks (last; run when the backend answers, before slice 2, about 3 h)**

Skipped on 2026-08-16 by owner decision (webservice degraded all day). The
exact selections to run are in the week-0 learning: `12411-0015` with
`regionalkey=03152,03156,03159`, years 2013 to 2017; `13211-02-05-4` on
Regionalstatistik with `contents=ERWP06,ERWP10`, `regionalkey=11000,03159`,
years 2014 to 2017 (needs that host's token); `12411-0010` all Länder, years
2021 to 2025. Extra things to record per payload, from the offline shape
work: the `time` format of `STAG` tables, whether `value_q` is present under
`quality=off`, the zip member name.

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
      With the same script: one `metadata/table` per pinned table (its
      `Structure.Rows[].Code` is the `regionalvariable` slice 4 needs) and
      one GET `catalogue/qualitysigns` without credentials (records
      whether it really runs unauthenticated, and whether the live
      `Parameter` echo is masked or real). Done state: a table in
      `learnings/` with those columns filled for all three.
- [ ] Merge the plan PR (#12) after review, with this checklist.

## Slice 1: reader seams and offline cache mode (WP-B, week 1, about 10 h)

Refactor only; M1 behavior unchanged. Everything a second locator type and a
POST reader need from the base class lands here.

All items below landed in fork PR #13
(https://github.com/TomKaltofen/mloda-plugin-govdata/pull/13, 2026-08-16,
CI green on 3.10 to 3.14, tox green).

- [x] 2026-08-16, PR #13. `reader.py`: `BaseGovDataReader(ReadFile,
      Generic[LocatorT])` with `LocatorT` bound to a `Locator` Protocol
      (`coerce`, `describe`) in `core/locator.py`; a `locator_type()`
      classmethod hook (base default `GovDataLocator`, one `cast`) drives
      `match_subclass_data_access` and `_coerce_locator`, and an
      already-coerced locator instance passes through unchanged (mloda hands
      the matched locator back to `load_data`). `_unknown_features_message`
      uses `describe()`.
- [x] 2026-08-16, PR #13. `core/provenance.py`: `Provenance(source, url,
      parameters, license, dataset)` and `FetchedPayload(path, sha256,
      retrieved_at, provenance)`. Decision: the sha256 is over the bytes
      stored in the cache only (for Destatis the raw zip); no second hash of
      an extracted member until a recipe needs one (slice 6 decides).
- [x] 2026-08-16, PR #13. `_fetch(locator, client) -> FetchedPayload`
      extracted; `_parse(path, locator, provenance, options)`;
      `ResolvedDistribution` stays exported.
- [x] 2026-08-16, PR #13. The mapping is `Provenance.from_distribution()` in
      `core/provenance.py` (not a method on `ResolvedDistribution`), so
      `provenance` imports `discovery` and not the reverse and every
      annotation resolves at runtime (a `TYPE_CHECKING`-only `Dataset` import
      broke `typing.get_type_hints`, which a pydantic recipe model would trip
      on). CKAN plus GET stays the base `_fetch`; the base raises
      `NotImplementedError` for a foreign locator type (a runtime guard; an
      intermediate CKAN class would let mypy enforce it instead, raised by
      review, kept as designed here, owner call).
- [x] 2026-08-16, PR #13. `GovDataReader._parse`, `bundeswahlleiterin.py`,
      `uba.py` updated; behavior unchanged.
- [x] 2026-08-16, PR #13. `core/cache.py`: `revalidate=False` returns the
      stored body with no request and raises `CacheMissError` naming the URL
      on a miss; meta stores `retrieved_at` (UTC, kept on a 304, it dates the
      bytes); meta without it or with a naive timestamp is a miss; the body
      path is derived from the meta's validated sha256, never from a stored
      file name (review finding: a tampered meta could point outside the
      cache directory, and the offline read would serve it forever).
- [x] 2026-08-16, PR #13. Tests as listed, plus: the provenance handed to
      `_parse` is the one `_fetch` produced, locator pass-through, cache
      meta hardening, runtime-resolvable annotations. Note: the fake reader
      is more than two lines because it must override `_fetch` and `_parse`.
- [x] 2026-08-16, PR #13. `NOTICE` backfilled for all six fixture files.
      Owner follow-up: the Berlin `Datenexport` license is not stated on the
      publisher's results and download pages; the `NOTICE` says so.
- [x] 2026-08-16, PR #13. `docs/adding-a-reader.md` paragraph added.
- [x] 2026-08-16. Commit `refactor: locator-generic reader with fetch seam
      and offline cache read` (PR #13).
- [x] 2026-08-16. Planning repo: ADR 0002 (module layout and reader seams),
      status proposed, committed locally (not pushed).

## Slice 2: Destatis credentials, client, envelope (WP-A, week 1, about 37 h)

Package `mloda_plugin_govdata/feature_groups/destatis/` with `core/` and
`tests/`. WP-A total 45 h = slice 0 (8 h) + this slice.

Landed in fork PR #14
(https://github.com/TomKaltofen/mloda-plugin-govdata/pull/14, 2026-08-16,
tox green). Items that need working credentials stay open below; the
GENESIS-Online webservice backend was still degraded that evening (every
`logincheck` answers the generic system error, guest and authenticated
alike) and no Regionalstatistik account exists yet, so the unauthenticated
and wrong-credential shapes were characterized on Regionalstatistik (healthy)
with made-up credentials. Learning:
`learnings/2026-08-16-genesis-envelope-shapes-on-healthy-host-and-guest-success-text.md`.

- [x] 2026-08-16, PR #14. Verified against v5.1, the pinned spec, and the
      observations: header credentials, token in `username` with empty
      `password`, body credentials ignored (guest `GAST`). New observation:
      a guest `logincheck` on a healthy host answers the *success text* next
      to `Username: GAST`, so success is "success text plus a real
      username", never the text alone. Recorded in ADR 0004 (planning repo,
      status proposed, committed locally).
- [x] 2026-08-16, PR #14. Contract test
      (`destatis/tests/test_contract.py`) over both pinned specs
      (`fixtures/openapi/`, `NOTICE` with URL, date, sha256): exact path
      and method per `(path, method)`, header credential declaration,
      every sendable field declared on the request body, the five relied-on
      defaults, and a NOTICE hash walk over every fixture file. Re-pinning
      is manual as described.
- [x] 2026-08-16, PR #14. Regionalstatistik as a second host: spec fixture
      committed; the contract test runs once per spec, request sides only,
      and asserts the known differences exactly (`data/chart2table`,
      `data/table`, GET on `profile/password` and `profile/removeResult`).
      Host table lives in `core/hosts.py` (`GenesisHost`: name, base URL,
      env prefix, registration page; `GENESIS_ONLINE`, `REGIONALSTATISTIK`,
      unknown hosts by explicit instance), re-exported from `core/api.py`.
- [x] 2026-08-16, PR #14. `core/auth.py` as specified; whitespace
      normalized; header-unsafe characters (control, non-latin-1) refused
      by field name (an httpx header error would print the value);
      `MissingCredentialsError` names the env vars, the free same-day
      registration and the host's start page; a token scoped to the other
      host raises `WrongHostCredentialsError`; env resolution never falls
      back across hosts.
- [x] 2026-08-16, PR #14. Env suffixes in a tuple (`ENV_SUFFIXES`); one
      scoped `# nosec B105` on the empty `password` header of the token path
      (verified live: bandit fires without it; it also prints a spurious
      "nosec encountered but no failed test" warning, harmless).
- [x] 2026-08-16, PR #14. `Options.context` key `genesis_credentials`,
      refused in `group`; only a `DestatisCredentials` instance is accepted
      (a plain mapping would sit unredacted in the context, which
      `str(options)` prints verbatim, review finding). Test asserts no
      secret in `repr(credentials)`, `str(credentials)`, `str(options)`.
      `DestatisLocator` is slice 4 and gets no credential field.
- [x] 2026-08-16, PR #14. `core/api.py`: `GenesisClient` over
      `build_client(follow_redirects=False)` (also per request, so an
      injected client cannot re-enable redirects); an explicit `Operation`
      registry (`whoami` GET, `logincheck`, `qualitysigns` GET,
      `metadata/table`, `data/tablefile` with its 25 fields);
      `request(endpoint, params)` refuses unregistered endpoints,
      undeclared fields, and non-string values before the wire, always
      sends `language`, resolves credentials lazily; `call()` inspects and
      raises typed errors with any quoted server text redacted. Auth
      failures are not retried (401, 404, and the `GAST` reply return on
      the first attempt; the M1 policy only retries transport errors and
      429/5xx; exhaustion becomes `GenesisBackendError`).
- [x] 2026-08-16, PR #14. D7 characterized: `THREADING` runs steps in
      threads of one process; `MULTIPROCESSING` spawns one fresh
      interpreter per compute framework instance (spawn context), and
      `load_data` receives no mode signal, so a refusal is not possible.
      Picked: per-host `threading.Lock` plus `filelock.FileLock` in the
      cache directory (`lock_dir`, default the M1 cache dir), taken per
      attempt so backoff runs unlocked, keyed by host name and base URL, a
      stuck holder fails loud after `LOCK_TIMEOUT_SECONDS`. Tests: two
      threads serialize under the in-process lock, a child process is
      blocked and later succeeds, the lock is free between attempts, a
      held lock file raises. D7 wording corrected in the plan (same
      commit). New dependency `filelock` (already in the lock file).
- [x] 2026-08-16, PR #14. `core/envelope.py` as specified: `GenesisStatus`
      (Type case-insensitive, `Error`/`Fehler`, `Warning`/`Warnung`),
      `GenesisIdent`, `GenesisEnvelope` (`Parameter` credentials stripped
      at parse time; `Object` -> `data`, `List` -> `entries`),
      `LoginCheckReply` flat with a redacting repr, `HelloWorldReply`, the
      flat body as a bare `GenesisStatus` (observed with HTTP 401 Code 15
      and HTTP 404 Code 2, not only 404). `inspect_response`: zip (refused
      on an HTTP error status), HTML -> `GenesisMaintenance`, JSON, else
      unknown; a recognized shape that fails validation raises
      `GenesisUnknownEnvelope` naming the fields only. Mapping: backend
      error text, then auth (Code 15 or the observed texts), job accepted
      (text), too large (Code 98), unknown table (Code 90), empty selection
      (Code 104), pass on 0 and 22, then the too-large text heuristic, else
      unknown with the status block quoted. Codes 90 and 98 and the
      job-accepted text come from pystatis, not from a capture yet
      (labeled in code, tests, and NOTICE).
- [x] 2026-08-16, PR #14. `scripts/capture_genesis_fixtures.py` with
      `core/redact.py` (case variants, URL-encoded forms, structural
      replacement of `username`/`password`/`Username`, guest marker and
      server masking kept, post-write check that no secret survived,
      redirects not captured); the synthetic-payload redaction test as
      specified. Used for every captured fixture in this PR.
- [ ] Fixtures: captured `whoami` (both hosts), guest `logincheck` (both
      hosts), `qualitysigns` (both hosts), 401 Code 15 (`metadata/table`
      guest), bad-credentials `logincheck` and `tablefile` 404 Code 2;
      documented `logincheck` ok and Code 104; synthetic maintenance HTML;
      both specs; `NOTICE` and `conftest.py` present. Still open (need
      working credentials): unknown-table, too-large, job-accepted
      envelopes; `metadata/table` per pinned table; the three week-0
      tablefile payloads (slice 0 live checks). Capture them with the
      script when GENESIS-Online's backend recovers or the Regionalstatistik
      account exists; then re-pin the code table.
- [x] 2026-08-16, PR #14. `genesis_live` marker registered and deselected
      by `addopts`; repo-root `conftest.py` skips `genesis_live` items with
      a reason naming all four env vars; `live` untouched.
- [x] 2026-08-16, PR #14. `docs/credentials.md` created.
- [x] 2026-08-16, PR #14. Tests as listed, plus: redirect refusal (own and
      injected client), warning-log redaction, validation-error redaction,
      empty-username logincheck, zip on HTTP error, non-string values, the
      NOTICE hash walk.
- [x] 2026-08-16, PR #14. Live smoke per host with per-host skip. Run that
      evening with the local token: GENESIS-Online raised
      `GenesisBackendError` (degraded backend, redacted text),
      Regionalstatistik skipped (no account). Owner: rerun when the backend
      answers; the "successful logincheck" item of slice 0 stays open.
- [x] 2026-08-16. Commit series landed as `feat(destatis): credentials,
      client, and status envelope mapping`, `test(destatis): fixtures,
      contract test, and client tests`, `chore: trim prose`,
      `fix(destatis): harden ...` (review round) in PR #14.

## Slice 3: parameter-keyed POST cache (WP-B, week 2, about 8 h)

Landed in fork PR #15
(https://github.com/TomKaltofen/mloda-plugin-govdata/pull/15, 2026-08-16,
tox green). Pulled forward from week 2 (owner call, no credentials needed).

- [x] 2026-08-16, PR #15. `destatis/core/cache.py`: `ParameterCache`, sibling
      of `DownloadCache` (no inheritance). Key: `post-` plus sha256 over
      canonical JSON of host base URL, endpoint, and the form fields as sent.
      Design change against the wording above: the parameters are the wire
      form, not a typed mirror of it, so what is keyed is what goes over the
      wire. `canonical_parameters(endpoint, parameters)` accepts only fields
      the operation registry declares (any other name is refused before
      keying or writing, named by field only, so a token under a stray name
      cannot leak), drops `username` / `password`, treats `None` as not
      sent, strips strings, turns ints into digits, comma-joins flat
      sequences, sorts the selection fields (`regionalkey`,
      `classifyingkey1..5`; other multi-values keep the caller's order),
      refuses bools (the spec spells them per field: `true`/`false` for
      `compress`, `on`/`off` for `quality`), and requires `language` where
      the operation declares it (the client would fill it in silently and
      two languages would share one entry). Meta: host, base URL, endpoint,
      canonical parameters, `retrieved_at` (UTC), sha256, data file. Body
      `post-<sha256>.bin` (content-addressed); the body path derives from the
      meta's validated sha256, never from the stored name; unreadable or
      undecodable meta, missing or naive timestamps, bad hashes, and
      unreadable bodies are misses; empty bodies refused; atomic writes.
- [x] 2026-08-16, PR #15. Freshness (D6): `get_or_fetch(host, endpoint,
      parameters, fetch, refresh=False)` calls `fetch(canonical)` only on a
      miss or with `refresh=True` (so a hit needs no credentials, the slice 4
      `peek` path); a served hit older than 30 days logs a warning naming
      the table and the age; no TTL. `lookup` (no request, `None` on a
      miss) and `store` are the primitives.
- [x] 2026-08-16, PR #15. Tests as listed, plus: canonical form and
      idempotence, undeclared and missing fields refused by name, secret
      under a stray name never written, non-ASCII and empty values, entries
      do not mix, second instance over the same directory, failed or empty
      refresh keeps the entry, six damaged-meta variants, unreadable body,
      meta `data_file` not trusted, no collision with the GET cache, the
      sent form equals the keyed mapping (real `GenesisClient` under respx).
- [x] 2026-08-16. Commit `feat(destatis): parameter-keyed POST cache` (PR #15).
- [x] 2026-08-16. Planning repo: ADR 0003 (cache), status proposed,
      committed locally (not pushed).
- [ ] Slice 4 note: `fetch` must raise for a reply that is not the payload
      (check `InspectedReply.kind == "zip"`); the `tablefile` builder owns
      the per-field wire spelling and passes one mapping to the cache.
      Whether the server treats `regionalkey` and `classifyingkey` as
      unordered sets shows in the live smoke as a wire finding, never as a
      wrong cache hit.

## Slice 4: tablefile, ffcsv parser, locator, reader (WP-B, week 2, about 32 h)

Checkpoint C1 target (Aug 30). Designed against the three real week-0
payloads, not a guess.

- [ ] `core/api.py`: `tablefile(...)` over the 25 spec fields: `name`,
      `area`, `compress` (empty rows and columns suppression, not zip),
      `transpose`, `contents`, `startyear`, `endyear`, `timeslices`,
      `regionalvariable`, `regionalkey`, `classifyingvariable1..5`,
      `classifyingkey1..5`, `format`, `quality` (default `off`; characterize
      `on` against one fixture, it is the quality-flag switch), `job`,
      `stand`, `language`. Wire policy (plan WP-B): every value a string
      (`true` / `false`, `jjjj`); `format=ffcsv`, `language`, `job=false`,
      `quality`, `compress=false`, `transpose=false` always sent; `area`,
      `stand`, `timeslices`, and unset selection fields not sent (server
      defaults; `area` values differ between spec `free` and PDF `Alle`,
      so no guessing). Test: the sent field set for a full locator equals
      the expected list, and never contains a name outside the spec's
      `tablefile` body (`regionalkeycode`, `classifyingkeycode1..3` exist
      only on the timeseries endpoints). Envelope and HTTP status inspected
      before any parsing.
- [ ] Zip handling from the week-0 characterization: reject empty archives
      and unexpected member sets; enforce a decompressed-size cap; the CSV
      member is written into the cache entry.
- [ ] ffcsv shape contract, written down in week 0 from Destatis' own example
      zip (`Aenderung_Struktur_Flatfile-CSV.zip`, sha256 `46c5bb2f...`) and
      confirmed against the three live payloads: fixed prefix
      `statistics_code; statistics_label; time_code; time_label; time`, N
      repeated blocks `{N}_variable_code; {N}_variable_label;
      {N}_variable_attribute_code; {N}_variable_attribute_label`, value block
      `value; value_unit; value_variable_code; value_variable_label;
      value_q`. Long format; the row key is (time, all attribute codes,
      `value_variable_code`, `value_unit`), because one `value_variable_code`
      can carry two units (`PREIS1` as `2020=100` and `%`). utf-8 with BOM,
      LF, semicolon, decimal comma in `de`, one CSV member per zip. The
      layout guard asserts the shape (block structure, no duplicates, all
      declared blocks present), not a literal name list, because width grows
      with the number of classifying variables. Test: the guard passes the
      three live fixtures and the three example files, raises on a hand-edited
      copy with a dropped block, and raises on the old-format example
      (`Statistik_Code; ...; <CODE>__<Label>__<Unit>`, German wide headers,
      shipped in the same zip) as the layout-drift case.
- [ ] Declared column schema per fixture, recorded before the parser is
      written: required columns and optional columns (quality flags) with
      their Arrow types, following the M1 rule that parsing needs explicit
      types (`parse.py` `_typed_table`, verified). Policy: optional columns
      are read when declared and absent otherwise; undeclared columns raise
      (this is how "quality flags if present" and "unknown columns raise"
      coexist). Live check inside this slice: whether `value_q` is present
      and empty or absent under `quality=off` (the examples were made with
      the flags on).
- [ ] `destatis/core/parse.py`: `parse_ffcsv_bytes(data, schema)` and path
      wrapper. Reuse `govdata/core/parse.detect_encoding`, `_clean_number`,
      `ZERO_MARKERS`, `NULL_MARKERS` (import, do not copy). `time` column
      parsed through the period model (until slice 7 lands, annual only as
      `int64` year with a TODO to the period model; the `time` format of
      `STAG` tables, `2015-12-31` or `31.12.2015`, is a live finding). A cell
      that cannot be typed raises with the offending cell and column.
- [ ] `value_marker` column (week 0 decision, plan D1 and section 6): the
      parser always emits the raw sign of the `value` cell (`-`, `.`, `...`,
      `/`, `x`, `()`, empty for numeric cells) as a string column next to the
      delivered `value_q`; `-` still types to 0, the null-like signs to null.
      Reason: GENESIS writes `-` for a Kreis outside its Gebietsstand
      validity (`03159` before 2016, `03152` and `03156` after 2016, on both
      hosts), and a silent 0 there is the U1/U2 hazard. Test: a `-` cell and
      a numeric `0` cell are distinguishable through `value_marker`, and the
      column is present on every Destatis table regardless of `quality`.
- [ ] `destatis/locator.py`: `DestatisLocator` (D10 validation): table code
      (`12411-0015` style and the Regionalstatistik `13211-02-05-4` style,
      both validated), optional region and classifying selection, optional
      `contents` (measure codes, D1), start and end year, `quality` (bool,
      default off), `host` (GENESIS-Online default, `regionalstatistik` as
      the second known name, D5), `language`, `format` pinned to `ffcsv`. Not locator fields in
      M2: `area`, `compress`, `transpose`, `timeslices`, `job`, `stand`
      (pinned wire values or not sent, documented in
      `docs/destatis-options.md`). Frozen (frozen dataclass with
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
- [ ] Fixtures: the three week-0 ffcsv zips plus an empty-result payload,
      and the six Destatis example files from `Aenderung_Struktur_Flatfile-CSV.zip`
      (three new-format `_flat.zip`, three old-format `_flat.csv`; Destatis
      2024, quotation permitted with attribution). `NOTICE` present.
- [ ] Tests: parser pinned to fixtures; zero-vs-missing (`-` is zero, `.`
      `...` `/` `x` `()` are null) per fixture; the marker sets pinned
      against the `qualitysigns` fixture from slice 2 (`0 - ... / . x ()
      p r s`, PDF 2.4.6): every fixture code is either in `ZERO_MARKERS`,
      in `NULL_MARKERS`, or a flag letter (`p`, `r`, `s`) that never
      becomes a value, so a new sign in a re-captured fixture fails
      loudly; decimal comma and thousands
      dot; int64 counts never via float; utf-8, BOM, and cp1252 variants;
      empty result yields the declared schema and `peek` lists columns;
      duplicate or extra columns raise; reader end to end via
      `mloda.run_all` with respx (fixture zip served); unknown feature error
      names available columns.
- [ ] Live smoke (`live` and `genesis_live`): one tiny table via
      `mloda.run_all`.
- [ ] README: Destatis quickstart snippet (credentials via env, one table).
- [ ] `docs/destatis-options.md` (about 2 h, counted under WP-G; step-0
      decision (c)): one table for `data/tablefile` with parameter, spec
      default, allowed values with the PDF section cited (2.5.12: `format`
      csv / datencsv / ffcsv / xlsx / genml / html, `language` de / en,
      booleans `true` / `false`, `startyear` / `endyear` `jjjj` 1900 to
      2100, `regionalkey` up to 8 digits with `*`, `contents` comma list),
      and the `DestatisLocator` field, the pinned wire value, or "not sent
      in M2" with the reason; a paragraph on `whoami` / `logincheck` and one
      on `qualitysigns` (written from the captured fixture, not the spec,
      which types its rows only as `{Code, Content}`). Skeleton rows may be
      printed from the pinned spec while authoring; the contract test keeps
      the names honest.
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
      `profile/removeResult`; camelCase per spec and PDF 2.7.2 URL, and
      its `name` field has no spec default, so the client validates it
      before sending): stretch, only after acceptance is green.
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
      Destatis annual (`12411-0015` and `12411-0010` are `STAG` reference
      dates 31.12., `13211-02-05-4` is `JAHR` annual average, verified in
      week 0 from the table structures); kerg is an election snapshot with
      no time column at all (verified: the header is `Nr;Gebiet;gehört
      zu;Gewählt ...`), so the election date comes from the locator or
      recipe, not the file; UBA `date_start` is an ISO string per hour. Write
      the Arrow representation down: `period_start` (date32) plus
      `frequency` (string) columns.
- [ ] `mloda_plugin_govdata/harmonization/__init__.py` (pure Python, no mloda
      import) and `harmonization/period.py`: `Period(start: date, freq)` with
      `freq` in `{year, quarter, month}` (the enum keeps the three values,
      only the annual parser ships in M2); `parse_genesis_time(label)` for
      the annual labels present in the chosen tables (`JAHR` `2015`, `STAG`
      `2015-12-31` or `31.12.2015`, whichever the live payload shows);
      `from_snapshot(date, freq)` for the election date; parser for UBA
      `date_start`.
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
- [-] Quarter and month parsing: dropped, cut line 2 was pre-pulled in slice
      0 (2026-08-16); the freed hours are banked buffer. Comes back only if
      a live payload forces it (decided at C1).
- [ ] Join plumbing (verified against mloda 0.10: `Link.inner_on` reads
      `index_columns()`, which `GovDataFeature` does not define; a
      `DestatisReader` feature and a `BundeswahlleiterinReader` feature both
      resolve to `GovDataFeature`, so discriminators are mandatory):
      `index_columns()` on the joining feature group(s) returning the Land
      key (kerg `Nr` on Land rows is already the AGS-2, week 0, so the join
      is `Nr` = `DLAND` with no name mapping); `Link.inner(...)` with
      `left_discriminator` / `right_discriminator` keyed on the reader
      option; the root-FeatureGroup decision from slice 4 applied. Test:
      `run_all(features, links=...)` over fixtures returns one joined table
      with 16 Land rows (Destatis fixture on the left, a kerg fixture with
      all 16 Land rows on the right; the committed sample has one Land row,
      `01;Schleswig-Holstein;99`, so the fixture is extended, not created).
- [ ] Commit series `feat(harmonization): period model`,
      `feat(govdata): Land-level join plumbing`.

## Slice 8: AGS-to-NUTS mapper (WP-D, weeks 1 and 4, about 45 h)

Standalone module, usable without mloda. Week 1 (about 10 h): extracts,
hand-verified mapping, and the packaging decision. Week 4 (about 35 h):
loaders, key model, edition model, mapping.

- [ ] Week 1: capture one small redistributable extract per reference source
      (Eurostat NUTS correspondence, LAU-to-NUTS, GV-ISys, BBSR
      Umsteigeschluessel Kreise) with URL and sha256 pinned; `NOTICE` with the
      Destatis, Eurostat, and BBSR long-form attributions. Already pinned in
      week 0 (URLs and hashes in the plan references): BBSR
      `ref-kreise-1990-2024.xlsx` (sha256 `68c4d001...`; extract the sheets
      `2013-2014`, `2015-2016`, `2020-2021`, header row plus the Göttingen,
      Osterode, Eisenach, Wartburgkreis, Cochem-Zell, Mayen-Koblenz and
      Rhein-Hunsrück rows) and GV-ISys `2016.xlsx` (sha256 `301a0b72...`;
      extract change `03/2016/0006-R`).
- [ ] Week 1: map five hand-picked AGS keys (Berlin `11000` as the
      city-state, `03159` Göttingen as the merged Kreis from slice 0, the
      Gemeindefreies Gebiet `03159501` Harz (Ldkr. Göttingen), formerly
      `03156501`, from the same GV-ISys change, and two ordinary Kreise) to
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
      keys repaired only when unambiguous by level and length, else raise
      (the BBSR Kreis file is the first real case: 8-digit `1001000` numbers
      whose first five digits are the Kreis and whose last three are always
      `000`, verified in week 0; repair `str(int(v)).zfill(8)[:5]` only
      when the `000` suffix holds); mixed levels in one input raise.
- [ ] `harmonization/reference/`: one loader per source (xlsx via openpyxl,
      GV100 fixed-width ASCII), each reading through the GET `DownloadCache`
      with `revalidate=False` by default (offline first, explicit refresh),
      pinned by URL plus sha256, with the fixture extract for tests. BBSR
      Kreis loader, from the week-0 characterization: one sheet per
      consecutive year pair named `<y>-<y+1>` (34 sheets, 1990 to 2024),
      header row 0, columns source key, source name, area share, population
      share, employee share, area, population and SvB weights, target key,
      target name; direction is old to new (forward) and is read from the
      sheet name; trailing all-empty rows end the data; a split source has
      several rows. Validity windows for keys come from GV-ISys change files
      and these sheets, never from labels (Regionalstatistik has no `(bis
      ...)` suffix).
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
      beyond) scoped to the source keys in the request, with the rest of the
      sheet reported, not raised (the real file's sheets `2014-2015` and
      `2015-2016` carry stale fractions on `07135` and `07137`, per-source
      sums 0.983 and 0.017, verified in week 0); every re-based value carries
      a flag column; observed values never replaced in place; a `-` cell
      whose key is outside its validity at that Stichtag is excluded and
      reported, never summed as 0; census breaks (2011, 2022) noted in output
      metadata, not smoothed.
- [ ] Expected-value fixture from slice 0, computed by hand 2026-08-16 (BBSR
      learning in the planning repo): source `12411-0015`,
      `regionalkey=03152,03156,03159`, 2013 to 2017, target Gebietsstand
      31.12.2016, key `ref-kreise-1990-2024.xlsx` sheet `2015-2016`
      population share, direction 2015 to 2016: `03159` re-based 322,616
      (2013), 324,013 (2014), 329,538 (2015), observed 327,065 (2016),
      328,036 (2017); inputs `03152` 248,249 / 250,220 / 255,653 and `03156`
      74,367 / 73,793 / 73,885. Fractional case, sheet `2013-2014`, 2013 to
      Gebietsstand 2014: `07135` 63,202 becomes 62,118 (share 0.9828486,
      exact), 1,084 moves to `07140` (100,770 becomes 101,854). Committed
      under `harmonization/tests/fixtures/` with the `NOTICE`; the input
      cells are re-read from the slice-2 live fixture before the test is
      pinned.
- [ ] Tests: hypothesis share-sum property; direction asserted from the key
      file's own metadata (sheet name, header years) in a fixture test;
      duplicated pairs and zero-share rows detected; the known stale-share
      defect is a fixture that the scoped check tolerates and the report
      names; the named multi-year Kreis series re-based across the slice-0
      Gebietsstand change matches the expected-value fixture cell for cell,
      with flag column and edition metadata asserted; the fractional case
      matches to the integer.
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
      (D2), used as a name check against the kerg Land rows (`gehört zu =
      99`, `Nr` = AGS-2, Bundesgebiet `Nr = 99` with empty `gehört zu`,
      verified in slice 0 on the full file), not as the join key.
- [ ] Recipe 1: population by Kreis over time, GENESIS-Online `12411-0015`
      over `03152`, `03156`, `03159`, 2013 to 2017, the U2 re-basing scenario;
      runs against fixture; compliance block filled; zero-vs-missing test
      uses `03159` before 2016 (`-`, not applicable) against a numeric cell.
- [ ] Recipe 2: Kreis-level labor-market indicator, Regionalstatistik
      `13211-02-05-4` with `contents=ERWP06,ERWP10` (Arbeitslose in Anzahl,
      Quote in %), the U1 rate-with-denominator scenario in one file (two
      `value_unit` values per key); zero-vs-missing test. Fallback if the
      Regionalstatistik path is not usable by then: `12521-0040` over
      `12411-0015` on GENESIS-Online, same scenario.
- [ ] Recipe 3: Destatis population by Land (GENESIS-Online `12411-0010`)
      joined with Bundestagswahl results by Land (D2, `Nr` = `DLAND`) through
      the slice 7 `links` block; the flagship integration test and the Demo
      Day story.
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
- [ ] `docs/credentials.md`: env names per host, both registration URLs
      (GENESIS-Online, Regionalstatistik), dual-path explanation, too-large
      guidance.
- [ ] `docs/destatis-options.md` (from slice 4): polish, link from the
      README Destatis section, mark stretch endpoint options as deferred.
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
- [x] 2. Quarter and month period parsing drop (slice 7). Pre-pulled in
      slice 0 on 2026-08-16 as banked buffer (all pinned tables are annual);
      reversible at C1.
- [ ] 3. Harmonization FeatureGroups drop to module plus notebook (slice 10;
      recipes 1 and 3 degrade as described in slice 11).
- [ ] 4. Retrofits shrink to one plus template (slice 11).

Never cut: compliance fields, zero-vs-missing tests, flags on harmonized
values, `tox` green.

## Stretch (only after acceptance is green)

- [ ] Full job path (submit, poll, download, remove), about 20 h.
- [ ] Gemeinde-level mapping, about 15 h.
- [-] Regionalstatistik host, about 10 h: moved into WP-A scope in slice 0
      (2026-08-16), recipe 2 needs it (slice 2 items).
- [ ] Discovery helper, about 8 h (kept out of AP2 by D5, re-checked in
      step 0): `describe_table(code)` typed by the spec's
      `TableMetadataEntry` (regional variable from `Structure.Rows[].Code`),
      `search_tables(term)` rows typed `{Code, Content, Time, Valid}`,
      `quality_signs()` rows `{Code, Content}`; starts from the slice-2
      fixtures; needs its own pagination and auth characterization.
