# Harmonization features

Three derived FeatureGroups turn a reader's columns into comparable ones. Each is a chained feature
(`<column>__<operation>`) that sits on top of the reader features: the reader locator you set on the
harmonized feature travels to the reader columns it needs, so one `Feature` describes the whole chain.

`HarmonizationFeature.cache_dir` holds the reference-table cache (BBSR keys, NUTS/LAU crosswalk,
GV-ISys changes) that `KreisRebaseFeature` and `AgsToNutsFeature` read; independent of
`BaseGovDataReader.cache_dir` (the reader's download cache), though both default to the same
location. `AnnualPeriodFeature` inherits the attribute but reads no reference table. Set
`HarmonizationFeature.cache_dir` itself, not one subclass's, to move every group's cache at once.

```python
from mloda.user import Feature, Options, mloda
from mloda_plugin_govdata.feature_groups.destatis import DestatisReader
from mloda_plugin_govdata.feature_groups.harmonization import KreisRebaseFeature  # noqa: F401 (registers the groups)

goettingen = {
    "name": "12411-0015",
    "regionalvariable": "KREISE",
    "regionalkey": ["03152", "03156", "03159"],
    "startyear": 2013,
    "endyear": 2017,
}
result = mloda.run_all(
    [
        Feature(
            "value__rebased",
            options={DestatisReader.__name__: goettingen, "rebase_from_year": 2015, "rebase_to_year": 2016},
        )
    ],
    compute_frameworks=["PyArrowTable"],
)
result[0]  # value__rebased~key, ~year, ~value, ~flag, ~sources, ~marker, ~issues, ~edition
```

Every group also takes an application-style name with the source column in `in_features` and the
parameters in the group options, the form a recipe file carries:

```python
Feature(
    "destatis__bevoelkerung__kreise",
    Options(
        group={DestatisReader.__name__: goettingen, "rebase_from_year": 2015, "rebase_to_year": 2016},
        context={"in_features": "value"},
    ),
)
```

Names are ASCII (`bevoelkerung`, not `Bevölkerung`). A result with several parts comes back as
`<name>~<part>` columns; request `<name>~<part>` to get one part alone, and chain onto a part to go on
(`value__rebased~key__nuts2024` maps the re-based keys). mloda returns one frame per FeatureGroup, so a
reader column requested next to a harmonized feature lands in its own frame.

## `value__rebased` (`KreisRebaseFeature`)

Re-bases Kreis observations onto a later Gebietsstand with the BBSR Umsteigeschluessel
(`harmonization/rebase.py`). Reads the ffcsv columns `1_variable_attribute_code` (variable block 1
must be `KREISE`), `time`, the value column and `value_marker`; the key sheet comes from the BBSR file
in the cache (`load_bbsr_kreise(cache, revalidate=True)` once, offline afterwards).

| Option | Meaning |
| --- | --- |
| `rebase_from_year`, `rebase_to_year` | the key sheet (`2015` and `2016` pick sheet `2015-2016`); required |
| `rebase_share` | `population` (default), `area`, or `employees` |
| `rebase_tolerance` | share-sum tolerance, renormalized inside, raises beyond |
| `rebase_on_unmatched`, `rebase_on_incomplete` | `raise` (default), `flag`, or `drop` |

Output, one row per Kreis and year: `~key`, `~year`, `~value` (float, never rounded), `~flag`
(`observed` or `rebased`), `~sources` (the contributing keys, `+`-joined), `~marker` (the raw GENESIS
sign of an observed cell), `~issues` (the issues that touch that row, `kind: detail`), and `~edition`
(JSON: source, URL, sha256, sheet, share, census breaks, and the full records of the issues no row
carries). The input rows do not survive; a partial sum or a key the sheet does not know raises unless
the policy says otherwise.

## `<key>__nuts2024` (`AgsToNutsFeature`)

Maps AGS keys through the pinned Eurostat LAU-to-NUTS crosswalk (`harmonization/nuts.py`). The edition
is part of the name (or the `nuts_version` option) and must be the one the cache holds
(`load_edition(cache, revalidate=True)` once). Kreis keys retired before the edition resolve through
the GV-ISys change files named in `AgsToNutsFeature.history_years` (the pinned year, fetched once with
`load_gv_isys_changes(year, cache, revalidate=True)`); Land keys are out of scope.

| Option | Meaning |
| --- | --- |
| `nuts_version` | `2024`; required in the configured form |
| `nuts_on_unmatched` | `raise` (default) or `flag` (null codes, the reason in `~unmatched`) |

Output, row-aligned with the input: `~key`, `~nuts1`, `~nuts2`, `~nuts3`, `~version`, `~unmatched`.

## `<time>__year_period` (`AnnualPeriodFeature`)

Turns a time column into the annual period start as `date32`: an integer year, a GENESIS JAHR or STAG
label, or a date on the 31 December reference date. A date inside the year (a 30 June Stichtag, an
election date) is refused: which annual period a snapshot joins to is a policy decision this group does
not make. `period_freq` is `year`; quarter and month are not built.

## Over other readers

`DestatisReader` leaves chained names to these groups. The other readers claim any name their option
key is set for, so a harmonized feature over them names its group: `Feature("Stichtag__year_period",
options={StuttgartPopulationReader.__name__: slug}, feature_group=AnnualPeriodFeature)`.
