[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/mloda-ai/mloda-plugin-govdata/blob/main/LICENSE)
[![mloda](https://img.shields.io/badge/built%20with-mloda-blue.svg)](https://github.com/mloda-ai/mloda)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://github.com/mloda-ai/mloda-plugin-govdata/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/mloda-ai/mloda-plugin-govdata/actions/workflows/test.yml?query=branch%3Amain)
[![Prototype Fund](https://img.shields.io/badge/Prototype%20Fund-Jahrgang%2002-f1c40f.svg)](https://prototypefund.de)

# mloda-plugin-govdata

Connectors for German open government data, built on [mloda](https://github.com/mloda-ai/mloda). Request the columns you want as mloda features; the plugin handles CKAN discovery, download with caching and retries, and parsing (German CSV or publisher JSON) into a typed Arrow table.

Three example datasets cover the M1 themes: population (GovData CSV), elections (Bundeswahlleiterin `kerg.csv`), and environment (UBA Air Data JSON).

## Status

Young but working. All three example readers run end to end, with paginated dataset search, cached downloads with retries, and unit plus property-based tests behind them. The elections and air-quality readers are thin subclasses of `GovDataReader` that override only the parse step; new datasets follow the same path (see [docs/adding-a-reader.md](docs/adding-a-reader.md)). Development happens in a 6-month Prototype Fund stage (June to November 2026), so the API may still shift between releases.

## Usage

Read the Stuttgart population dataset (via GovData) as a typed PyArrow table:

```python
from mloda.user import Feature, mloda
from mloda_plugin_govdata.feature_groups.govdata import GovDataReader

slug = "einwohner-nach-altersgruppen-und-stadtbezirken"
result = mloda.run_all(
    [
        Feature("Einwohner", options={GovDataReader.__name__: slug}),
        Feature("Stadtbezirk", options={GovDataReader.__name__: slug}),
    ],
    compute_frameworks=["PyArrowTable"],
)
table = result[0]  # pyarrow.Table with the requested columns
```

The option value is a GovData dataset slug or a direct distribution URL. The license is read from the CKAN distribution metadata. Set `GovDataReader.cache_dir` to control where downloads are cached.

Don't know the slug yet? Search GovData with the paginated CKAN `package_search` API:

```python
from mloda_plugin_govdata.feature_groups.govdata import search_datasets
from mloda_plugin_govdata.feature_groups.govdata.client import build_client

with build_client() as client:
    for dataset in search_datasets(client, "einwohner stuttgart", max_results=10):
        print(dataset.name, "|", dataset.title)
```

`search_datasets` walks the result pages lazily (`page_size` per request) and stops at `max_results` or the end of the result set.

The elections reader handles a direct CSV URL whose file has a multi-row merged header (Bundeswahlleiterin `kerg.csv`):

```python
from mloda_plugin_govdata.feature_groups.govdata import BundeswahlleiterinReader

kerg = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv"
result = mloda.run_all(
    [Feature("Gebiet", options={BundeswahlleiterinReader.__name__: kerg})],
    compute_frameworks=["PyArrowTable"],
)
```

The header geometry defaults to the btw25 `kerg.csv` layout and is overridable per feature via the `OPTION_WAHL_*` option keys, so a differently shaped election export is a configuration step instead of a code change. The single-header wahlen-berlin.de Datenexport files use the degenerate geometry:

```python
from mloda_plugin_govdata.feature_groups.govdata import (
    OPTION_WAHL_HEADER_ROWS,
    OPTION_WAHL_LABEL_COLUMNS,
    OPTION_WAHL_SKIPROWS,
    OPTION_WAHL_VALUE_TYPE,
    BundeswahlleiterinReader,
)

berlin = "https://www.wahlen-berlin.de/wahlen/BE2023/AFSPRAES/agh/Datenexport_AGH2023_Zweitstimme_W_BE.csv"
options = {
    BundeswahlleiterinReader.__name__: berlin,
    OPTION_WAHL_SKIPROWS: 0,
    OPTION_WAHL_HEADER_ROWS: 1,
    OPTION_WAHL_LABEL_COLUMNS: 12,
    OPTION_WAHL_VALUE_TYPE: "float",
}
result = mloda.run_all(
    [Feature("Bezirksname", options=options), Feature("Gueltig", options=options)],
    compute_frameworks=["PyArrowTable"],
)
```

The environment reader fetches the Umweltbundesamt (UBA) Air Data v4 `measures` endpoint (REST JSON) and flattens it to one typed row per station and timestamp. `uba_measures_url` builds the query (here: hourly ozone at station 143):

```python
from mloda_plugin_govdata.feature_groups.govdata import UbaAirReader, uba_measures_url

url = uba_measures_url(station=143, component=3, scope=2, date_from="2025-01-01", date_to="2025-01-01")
result = mloda.run_all(
    [
        Feature("date_start", options={UbaAirReader.__name__: url}),
        Feature("value", options={UbaAirReader.__name__: url}),
    ],
    compute_frameworks=["PyArrowTable"],
)
```

Columns are `station_id`, `date_start`, `component_id`, `scope_id`, `value`, `date_end`, and `index` (the air-quality index). Component and scope ids come from the UBA `components` and `scopes` endpoints.

## Demo

Two interactive [marimo](https://marimo.io) notebooks live in the repository (not in the published package), so run them from a source checkout:

```bash
git clone https://github.com/TomKaltofen/mloda-plugin-govdata.git
cd mloda-plugin-govdata
uv sync --all-extras
uv run marimo edit demos/govdata_demo.py
uv run marimo edit demos/berlin_wahl_2026_demo.py
```

`govdata_demo.py` walks through dataset discovery and the three example datasets. `berlin_wahl_2026_demo.py` connects Berlin's open voting data (AGH 2023, EU 2024, BT 2025 at Wahlbezirk level, plus Strukturdaten and the official 2023-on-2026-geometry baseline) and ends in a waiting config cell that switches the notebook to the live preliminary results on election night, 20 September 2026, with no code change.

The notebooks hit the live GovData, Bundeswahlleiterin, wahlen-berlin.de, statistik-berlin-brandenburg.de, and UBA endpoints; downloads are cached locally after the first run.

## Related Repositories

- **[mloda](https://github.com/mloda-ai/mloda)**: the core library this plugin builds on. You declare which features you need; mloda resolves how to compute them.

- **[mloda-registry](https://github.com/mloda-ai/mloda-registry)**: plugin registry and development guides for the mloda ecosystem.

## Funding

Developed as part of the [Prototype Fund](https://prototypefund.de) (Round 2 / Jahrgang 02), funded by the German Federal Ministry of Research, Technology and Space (BMFTR) and supported by the [Open Knowledge Foundation Deutschland](https://okfn.de). Funding code (Förderkennzeichen): **16IS26S11**. Stage 1 funding period: 6 months from June 2026.

<p>
  <img src="logos/bmftr.png" alt="Funded by the Federal Ministry of Research, Technology and Space (BMFTR)" height="110">
  &nbsp;&nbsp;&nbsp;
  <img src="logos/prototypefund.png" alt="Supported by the Prototype Fund" height="110">
</p>

