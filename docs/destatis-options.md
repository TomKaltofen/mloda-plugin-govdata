# Destatis (GENESIS) options

`DestatisReader` reads one GENESIS `data/tablefile` selection (Anwenderdokumentation "Webservice/API"
v5.1, section 2.5.12) as ffcsv. This page is the parameter surface: what `DestatisLocator` exposes,
what is pinned to a fixed wire value, and what is never sent.

## Option forms

The reader option value is a bare table code, a `DestatisLocator`, or its dict form (JSON-native, the
shape a recipe file carries); all three coerce to the same locator:

```python
from mloda.user import Feature
from mloda_plugin_govdata.feature_groups.destatis import DestatisLocator, DestatisReader

Feature("value", options={DestatisReader.__name__: "12411-0010"})
Feature("value", options={DestatisReader.__name__: DestatisLocator("12411-0015", regionalvariable="KREISE")})
Feature("value", options={DestatisReader.__name__: {"name": "12411-0015", "regionalvariable": "KREISE"}})
```

The one locator field that is not a `data/tablefile` parameter is `host` (`genesis`, the default, or
`regionalstatistik`; registrations are per host, see [credentials.md](credentials.md)); `language` is sent,
pinned to `de` (see the table). The selection is validated at construction: an unknown table code shape, a
year outside 1900 to 2100, `startyear` after `endyear`, or an unknown dict key fails before any request.

## `data/tablefile` parameters

| Parameter | Spec default | Allowed values | `DestatisLocator` field / policy |
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
| `job` | `false` | `true`, `false` | pinned `false`; the job path is deferred (see below) |
| `stand` | (none) | date | not sent; server default applies |
| `language` | `de` | `de`, `en` | pinned `de`; `parse_ffcsv_bytes` assumes German decimal-comma formatting, so `en` is rejected rather than silently corrupting values |

`area`'s allowed values differ between the OpenAPI spec (`free`/`public`/`user`) and the PDF
documentation (`Alle`/...); the connector leaves it at the server default rather than guessing which is current.

## Output columns

The reader returns the parsed ffcsv table, one row per value cell:

| Column | Type | Holds |
|---|---|---|
| `statistics_code`, `statistics_label` | string | the statistic (`12411`, `Fortschreibung des Bevölkerungsstandes`) |
| `time_code`, `time_label` | string | the time dimension: `JAHR` / `Jahr` or `STAG` / `Stichtag` |
| `time` | int64 | the year, parsed from the JAHR (`2015`) or STAG (`2015-12-31`) value; the raw value is not kept |
| `{N}_variable_code`, `{N}_variable_label`, `{N}_variable_attribute_code`, `{N}_variable_attribute_label` | string | one block per variable, `N` from 1; block 1 is usually the region (`1_variable_code` `KREISE`, its key `03159` in `1_variable_attribute_code`) |
| `value` | float64 | the number; a `-` reads as 0, the other signs as null |
| `value_unit`, `value_variable_code`, `value_variable_label` | string | the measure (`Anzahl`, `BEVSTD`, `Bevölkerungsstand`) |
| `value_q` | string | the quality flag, only with `quality=True` |
| `value_marker` | string | the raw sign of the `value` cell (`-`, `.`, `...`, `/`, `x`, `()`), `""` for a number |

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

## Deferred

Not built. The reader sends only the pinned wire values above and accepts none of these as options:

- The job path: `job=true`, polling the job list, downloading and removing the result. A table over the
  download limit raises `GenesisResultTooLarge` instead; see [credentials.md](credentials.md#result-too-large).
- `area`, `stand`, and `timeslices` as locator fields; the server defaults apply.
- `language=en`: the ffcsv parser reads German number formatting only.
- Discovery: `catalogue/qualitysigns` is the only catalogue endpoint the client knows; `GenesisClient`
  refuses every endpoint outside its registered operations, so the remaining catalogue and find endpoints
  cannot be called, and `metadata/table` is callable but neither typed nor used by the reader. Table codes and dimension codes come from the host's web portal.
