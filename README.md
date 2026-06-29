[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/mloda-ai/mloda-plugin-govdata/blob/main/LICENSE)
[![mloda](https://img.shields.io/badge/built%20with-mloda-blue.svg)](https://github.com/mloda-ai/mloda)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://github.com/mloda-ai/mloda-plugin-govdata/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/mloda-ai/mloda-plugin-govdata/actions/workflows/test.yml?query=branch%3Amain)
[![Prototype Fund](https://img.shields.io/badge/Prototype%20Fund-Jahrgang%2002-f1c40f.svg)](https://prototypefund.de)

# mloda-plugin-govdata

Connectors for German open government data, built on [mloda](https://github.com/mloda-ai/mloda). Request the columns you want as mloda features; the plugin handles CKAN discovery, download with caching and retries, and German-CSV parsing into a typed Arrow table.

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

## Related Repositories

- **[mloda](https://github.com/mloda-ai/mloda)**: The core library for open data access. Declaratively define what data you need, not how to get it. mloda handles feature resolution, dependency management, and compute framework abstraction automatically.

- **[mloda-registry](https://github.com/mloda-ai/mloda-registry)**: The central hub for discovering and sharing mloda plugins. Browse community-contributed FeatureGroups, find integration guides, and publish your own plugins for others to use.

## Funding

Developed as part of the [Prototype Fund](https://prototypefund.de) (Round 2 / Jahrgang 02), funded by the German Federal Ministry of Research, Technology and Space (BMFTR) and supported by the [Open Knowledge Foundation Deutschland](https://okfn.de). Funding code (Förderkennzeichen): **16IS26S11**. Stage 1 funding period: 6 months from June 2026.

<p>
  <img src="logos/bmftr.png" alt="Funded by the Federal Ministry of Research, Technology and Space (BMFTR)" height="110">
  &nbsp;&nbsp;&nbsp;
  <img src="logos/prototypefund.png" alt="Supported by the Prototype Fund" height="110">
</p>

