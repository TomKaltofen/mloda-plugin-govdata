# Destatis (GENESIS) options

`DestatisReader` reads one GENESIS `data/tablefile` selection (Anwenderdokumentation "Webservice/API"
v5.1, section 2.5.12) as ffcsv. This is the M2 parameter surface: what `DestatisLocator` exposes,
what is pinned to a fixed wire value, and what is never sent.

## `data/tablefile` parameters

| Parameter | Spec default | Allowed values | `DestatisLocator` field / M2 policy |
|---|---|---|---|
| `name` | (required) | table code, up to 15 chars | `name` (required; validated as a GENESIS-Online `12411-0015` or Regionalstatistik `13211-02-05-4` style code) |
| `area` | `free` | `free`, `public`, `user` (spec) / `Alle`, ... (PDF; the two disagree, see below) | not sent; server default applies |
| `compress` | `false` | `true`, `false` | pinned `false` (empty rows/columns suppression is not zip compression) |
| `transpose` | `false` | `true`, `false` | pinned `false` |
| `contents` | (none) | comma-separated measure codes | `contents` |
| `startyear` / `endyear` | (none) | `jjjj`, 1900-2100 | `startyear` / `endyear` |
| `timeslices` | (none) | integer | not sent; server default applies |
| `regionalvariable` | (none) | region dimension code | `regionalvariable` |
| `regionalkey` | (none) | up to 8 digits per key, `*` wildcard, comma list | `regionalkey` (sequence, sorted on the wire by `ParameterCache`) |
| `classifyingvariable1..5` | (none) | classifying dimension code | `classifyingvariable1..5` |
| `classifyingkey1..5` | (none) | comma list | `classifyingkey1..5` (sequence, sorted on the wire) |
| `format` | `datencsv` | `csv`, `datencsv`, `ffcsv`, `xlsx`, `genml`, `html` | pinned `ffcsv`; not a locator field (always this value) |
| `quality` | `off` | `on`, `off` | `quality` (bool; `True` sends `on`) |
| `job` | `false` | `true`, `false` | pinned `false`; the job path (batch results for oversized tables) is not built |
| `stand` | (none) | date | not sent; server default applies |
| `language` | `de` | `de`, `en` | pinned `de`; `parse_ffcsv_bytes` assumes German decimal-comma formatting, so `en` is rejected rather than silently corrupting values |

`area`'s allowed values differ between the OpenAPI spec (`free`/`public`/`user`) and the PDF
documentation (`Alle`/...); M2 leaves it at the server default rather than guessing which is current.

## `whoami` / `logincheck`

`helloworld/whoami` (GET, no credentials) echoes the client's own `User-Agent` as a connectivity
check. `helloworld/logincheck` (POST, credentials required) proves the credentials: the server
always answers HTTP 200 with a success or failure text in the body, never a 401. See
[docs/credentials.md](credentials.md) for how a guest reply is treated.

## `qualitysigns`

`catalogue/qualitysigns` (GET, `language`, no credentials) is the value-marker legend: a `List` of
`Code`/`Content` pairs. Captured from the live GENESIS-Online catalogue (see the fixture
`genesis-guest-qualitysigns.json`), not the spec, which only types the rows structurally. Every
code in the legend is either a `ZERO_MARKERS` or `NULL_MARKERS` member the ffcsv parser recognizes,
or a `value_q` flag letter (`p`, `r`, `s`) that never appears in the `value` cell itself
(`test_qualitysigns_legend_is_covered_by_zero_null_or_a_flag` pins this).
