# Adding a Reader

`GovDataReader` (in `mloda_plugin_govdata/feature_groups/govdata/reader.py`) does the plumbing: locator coercion, CKAN discovery, cached download with retries, and column selection. Subclasses override `_parse`, plus `suffix` when the payload is not CSV. `BundeswahlleiterinReader` and `UbaAirReader` show the pattern.

To connect a new dataset:

1. Check whether `GovDataReader` already handles it. A GovData slug or a direct CSV URL with a regular single-row header needs no code; unknown columns are read as strings. For typed columns, add a schema next to `POPULATION_SCHEMA` and wire it into `_schema_for`.
2. Otherwise, subclass `GovDataReader` and override `_parse` (and `suffix` for non-CSV payloads).
3. Keep the parse logic in its own module as a `parse_*_bytes` function plus a path wrapper, like `parse.py` and `uba.py`. That keeps it testable from fixture files without network access.
4. Add tests under `mloda_plugin_govdata/feature_groups/govdata/tests/` with a small real sample in `tests/fixtures/`.
5. Export the reader from `feature_groups/govdata/__init__.py` and add a usage snippet to the README.
6. Run `tox` (pytest, ruff, mypy strict, bandit); it must pass before a PR.
