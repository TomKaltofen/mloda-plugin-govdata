[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/mloda-ai/mloda-plugin-govdata/blob/main/LICENSE)
[![mloda](https://img.shields.io/badge/built%20with-mloda-blue.svg)](https://github.com/mloda-ai/mloda)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://github.com/mloda-ai/mloda-plugin-govdata/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/mloda-ai/mloda-plugin-govdata/actions/workflows/test.yml?query=branch%3Amain)
[![Prototype Fund](https://img.shields.io/badge/Prototype%20Fund-Jahrgang%2002-f1c40f.svg)](https://prototypefund.de)

# mloda-plugin-govdata

Connectors for German open government data, built on [mloda](https://github.com/mloda-ai/mloda). Request the columns you want as mloda features; the plugin handles CKAN discovery, download with caching and retries, and parsing (German CSV or publisher JSON) into a typed Arrow table.

Three example datasets cover population (GovData CSV), elections (Bundeswahlleiterin `kerg.csv`), and environment (UBA Air Data JSON); the Destatis connector adds GENESIS tables, with harmonization features and recipe files on top.

## Status

Young but working. The three example readers and the Destatis connector run end to end, with paginated dataset search, cached downloads with retries, and unit plus property-based tests behind them. Every reader is a thin subclass of `BaseGovDataReader` that overrides the parse step (and the fetch or read step for a non-GovData source); new datasets follow the same path (see [docs/adding-a-reader.md](https://github.com/mloda-ai/mloda-plugin-govdata/blob/main/docs/adding-a-reader.md)). Development happens in a 6-month Prototype Fund stage (June to November 2026), so the API may still shift between releases.

## Usage

Read the Stuttgart population dataset (via GovData) as a typed PyArrow table:

```python
from mloda.user import Feature, mloda
from mloda_plugin_govdata.feature_groups.govdata import StuttgartPopulationReader

slug = "einwohner-nach-altersgruppen-und-stadtbezirken"
result = mloda.run_all(
    [
        Feature("Einwohner", options={StuttgartPopulationReader: slug}),
        Feature("Stadtbezirk", options={StuttgartPopulationReader: slug}),
    ],
    compute_frameworks=["PyArrowTable"],
)
table = result[0]  # pyarrow.Table with the requested columns
result.plan  # resolved execution steps: which FeatureGroup ran on which framework
```

The options key is the reader class or its class-name string; both select the same reader. The option value is a GovData dataset slug or a direct distribution URL. The license is read from the CKAN distribution metadata. Set `BaseGovDataReader.cache_dir` to control where downloads are cached. For any other GovData CSV dataset, `GovDataReader` works out of the box and reads every column as a string; subclass it and set `schema` for typed columns.

Don't know the slug yet? Search GovData with the paginated CKAN `package_search` API:

```python
from mloda_plugin_govdata.feature_groups.govdata import build_client, search_datasets

with build_client() as client:
    for dataset in search_datasets(client, "einwohner stuttgart", max_results=10):
        print(dataset.name, "|", dataset.title)
```

`search_datasets` walks the result pages lazily (`page_size` per request) and stops at `max_results` or the end of the result set.

Got a slug but not the column names? `peek` lists what you can request as features:

```python
StuttgartPopulationReader.peek(slug)  # {"Stichtag": "date32[day]", "Stadtbezirk": "string", ...}
```

It works on every reader (`BundeswahlleiterinReader.peek(kerg)`, `UbaAirReader.peek(url)`) and downloads through the cache, so the actual feature request reuses the file. A typo in a feature name fails with the available columns and a close-match suggestion instead of a raw KeyError.

The elections reader handles a direct CSV URL whose file has a multi-row merged header (Bundeswahlleiterin `kerg.csv`):

```python
from mloda_plugin_govdata.feature_groups.govdata import BundeswahlleiterinReader

kerg = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv"
result = mloda.run_all(
    [Feature("Gebiet", options={BundeswahlleiterinReader: kerg})],
    compute_frameworks=["PyArrowTable"],
)
```

The environment reader fetches the Umweltbundesamt (UBA) Air Data v4 `measures` endpoint (REST JSON) and flattens it to one typed row per station and timestamp. `uba_measures_url` builds the query (here: hourly ozone at station 143):

```python
from mloda_plugin_govdata.feature_groups.govdata import UbaAirReader, uba_measures_url

url = uba_measures_url(station=143, component=3, scope=2, date_from="2025-01-01", date_to="2025-01-01")
result = mloda.run_all(
    [
        Feature("date_start", options={UbaAirReader: url}),
        Feature("value", options={UbaAirReader: url}),
    ],
    compute_frameworks=["PyArrowTable"],
)
```

Columns are `station_id`, `date_start`, `component_id`, `scope_id`, `value`, `date_end`, and `index` (the air-quality index). Component and scope ids come from the UBA `components` and `scopes` endpoints.

The Destatis connector reads a GENESIS table (Statistisches Bundesamt or a Regionalstatistik
installation) by table code, needs a free registration (`GENESIS_TOKEN` or `GENESIS_USER` /
`GENESIS_PASSWORD`; see [docs/credentials.md](docs/credentials.md)), and parses the ffcsv reply:

```python
from mloda_plugin_govdata.feature_groups.destatis import DestatisReader

result = mloda.run_all(
    [
        Feature(
            "value",
            options={
                DestatisReader.__name__: {
                    "name": "12411-0015",
                    "regionalvariable": "KREISE",
                    "regionalkey": ["03159"],
                    "startyear": 2016,
                    "endyear": 2016,
                }
            },
        )
    ],
    compute_frameworks=["PyArrowTable"],
)
```

The option value is a bare table code, a `DestatisLocator`, or the dict form above (JSON-native, so
it round-trips through a recipe file); see [docs/destatis-options.md](docs/destatis-options.md) for
the full parameter table. `peek` lists the ffcsv columns the same way as the other readers.

Harmonized features sit on top of the reader columns: `value__rebased` re-bases a Kreis series onto a
later Gebietsstand with the BBSR keys, `1_variable_attribute_code__nuts2024` adds NUTS codes, and
`time__year_period` types the period. The re-based series carries its flags, sources, issues and key
edition as columns; see [docs/harmonization.md](docs/harmonization.md).

```python
from mloda_plugin_govdata.feature_groups.govdata import DownloadCache
from mloda_plugin_govdata.feature_groups.harmonization import KreisRebaseFeature  # registers the groups
from mloda_plugin_govdata.harmonization.reference.bbsr import load_bbsr_kreise

with DownloadCache(KreisRebaseFeature.cache_dir) as cache:
    load_bbsr_kreise(cache, revalidate=True)  # the BBSR key file, fetched once and read offline afterwards

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

A recipe file bundles the features, joins, and provenance of one run as JSON; `load_recipe` returns what
`mloda.run_all` needs plus the compliance block (license, attribution, payload sha256, credential env names).
Recipes ship under `recipes/` in the repository, not in the published package: the Land table, the re-based Kreis series, a rate with its denominator, the
Land-level join, and the three example datasets above. See [docs/recipes.md](docs/recipes.md).

```python
from mloda_plugin_govdata.recipes import load_recipe

recipe = load_recipe("recipes/land_population.json")
result = mloda.run_all(recipe.features, compute_frameworks=["PyArrowTable"], links=set(recipe.links))
recipe.compliance.sources[0].attribution  # what to print next to the result
```

## Demo

An interactive [marimo](https://marimo.io) notebook walks through dataset discovery, all three example datasets, and two shipped recipes over Destatis tables (population per eligible voter by Land, a Kreis series re-based across a merger). The notebook lives in the repository (not in the published package), so run it from a source checkout:

```bash
git clone https://github.com/mloda-ai/mloda-plugin-govdata.git
cd mloda-plugin-govdata
uv sync --all-extras
uv run marimo edit demos/govdata_demo.py
```

The notebook hits the live GovData, Bundeswahlleiterin, UBA, and GENESIS-Online endpoints and fetches the BBSR key file; downloads are cached locally after the first run. The Destatis chapter needs GENESIS-Online credentials in the environment (`GENESIS_TOKEN`, or `GENESIS_USER` and `GENESIS_PASSWORD`; see [docs/credentials.md](docs/credentials.md)) and skips itself without them.

## Related Repositories

- **[mloda](https://github.com/mloda-ai/mloda)**: the core library this plugin builds on. You declare which features you need; mloda resolves how to compute them.

- **[mloda-registry](https://github.com/mloda-ai/mloda-registry)**: plugin registry and development guides for the mloda ecosystem.

## Funding

Developed as part of the [Prototype Fund](https://prototypefund.de) (Round 2 / Jahrgang 02), funded by the German Federal Ministry of Research, Technology and Space (BMFTR) and supported by the [Open Knowledge Foundation Deutschland](https://okfn.de). Funding code (Förderkennzeichen): **16IS26S11**. Stage 1 funding period: 6 months from June 2026.

<p>
  <img src="https://raw.githubusercontent.com/mloda-ai/mloda-plugin-govdata/main/logos/bmftr.png" alt="Funded by the Federal Ministry of Research, Technology and Space (BMFTR)" height="110">
  &nbsp;&nbsp;&nbsp;
  <img src="https://raw.githubusercontent.com/mloda-ai/mloda-plugin-govdata/main/logos/prototypefund.png" alt="Supported by the Prototype Fund" height="110">
</p>

