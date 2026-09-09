# Recipes

A recipe is one JSON file naming the features a run needs, the joins between them, and where the data
came from. `load_recipe(path)` returns the mloda feature list, the `Link` objects, and the compliance
block; `write_recipe` produces the file from Python objects.

```python
from mloda.user import mloda
from mloda_plugin_govdata.recipes import load_recipe

recipe = load_recipe("recipes/land_population.json")
result = mloda.run_all(recipe.features, compute_frameworks=["PyArrowTable"], links=set(recipe.links))
recipe.compliance.sources[0].attribution  # what to print next to the result
```

## File shape

```json
{
  "features": [
    {"name": "value", "options": {"DestatisReader": {"name": "12411-0010", "startyear": 2024, "endyear": 2024}}},
    {"name": "Nr", "options": {"BundeswahlleiterinReader": "https://www.bundeswahlleiterin.de/.../kerg.csv"}}
  ],
  "links": [
    {
      "join": "inner",
      "left": {"feature_group": "GovDataFeature", "index": ["1_variable_attribute_code"],
               "discriminator": {"DestatisReader": {"name": "12411-0010", "startyear": 2024, "endyear": 2024}}},
      "right": {"feature_group": "GovDataFeature", "index": ["Nr"],
                "discriminator": {"BundeswahlleiterinReader": "https://www.bundeswahlleiterin.de/.../kerg.csv"}}
    }
  ],
  "compliance": {
    "sources": [
      {
        "license": "dl-de/by-2-0",
        "attribution": "(c) Statistisches Bundesamt (Destatis), 2026",
        "dataset_uri": "https://genesis.destatis.de/datenbank/online/statistic/12411/table/12411-0010",
        "retrieved_at": "2026-09-08T00:00:00Z",
        "sha256": "aba0f99e3b8eef1f4d975c0e2ed3d7323024dd8a798dbd875e35ae34447f3916",
        "modifications": ["ffcsv reply parsed into a typed table"],
        "credential_env": ["GENESIS_TOKEN"]
      }
    ],
    "notes": "optional: census breaks, caveats"
  }
}
```

- `features`: mloda's feature-config array, handed to `load_features_from_config` unchanged. Items are
  feature names or objects with `name`, `options` (or `group_options` plus `context_options`),
  `in_features`, `propagate_context_keys`, `column_index`, `feature_group` (a class name). Reader locators
  are strings or dicts (the `DestatisLocator` dict form). Any other key fails at load with the allowed set.
- `links`: joins the feature array cannot express. `join` is `inner`, `left`, `right`, `outer`, `append`,
  or `union`; each side names the FeatureGroup class, its key columns, and, when both sides share a class,
  a `discriminator` of option key/value pairs picking the node. mloda matches a discriminator by exact
  equality with the feature's option value, so use the same locator form on both sides.
- `compliance.sources`: one entry per data source with `license`, `attribution`, `dataset_uri`,
  `retrieved_at` (timezone-aware), the payload `sha256`, `modifications` (what the reader changes; dl-de/by-2-0
  requires marking changes), and `credential_env` (the env-var names the source needs, never values).

## What round-trips

The writer covers the option values this plugin produces: strings, numbers, booleans, lists, dicts, a
`DestatisLocator` (its dict form, `None` fields omitted), a `GovDataLocator` with default `ckan_base` and
`resource_index` (its slug or URL), `in_features`, the `feature_group` scope, and `propagate_context_keys`.
A `Feature` with `data_type`, `index`, `domain`, or `compute_framework` set through the constructor, a nested
`Feature` inside `in_features`, or an `asof` link raises instead of being dropped. A link set on a `Feature`
is hoisted into `links`.

## Credentials never go in a recipe

Validation rejects a credential-named key anywhere (`username`, `password`, `token`, `genesis_credentials`,
...), a token-shaped value (24 or more letters and digits with no separator, outside `sha256`), an entry in
`credential_env` that is not an env-var name, and any value of the process's own `GENESIS_*` or
`REGIONALSTATISTIK_*` variables found in the file. Error messages name the location, never the value.
Credentials resolve from the environment at run time; see [credentials.md](credentials.md).

## Where recipe files live

Repo-root `recipes/`, outside the wheel: the package ships code only, the same policy as the reference
tables in the harmonization package. Test recipes sit next to their tests.
