# Adding a Reader

`BaseGovDataReader` (in `mloda_plugin_govdata/feature_groups/govdata/reader.py`) does the plumbing: locator coercion, CKAN discovery, cached download with retries, and column selection. Subclasses implement `_parse` (or, for plain CSVs, just set `schema` on a `GovDataReader` subclass), plus `suffix` when the payload is not CSV. Each data source lives in its own module (`population.py`, `bundeswahlleiterin.py`, `uba.py`); shared source-agnostic code (client, cache, discovery, locator, CSV parsing) lives in `core/`.

`BaseGovDataReader` is generic over its locator type: any class with `coerce(value) -> locator | None` (option value to locator, `None` when the value isn't usable) and `describe() -> str` (a label for error messages), with `GovDataLocator` as the built-in one. The fetch seam is `_fetch(locator, client) -> FetchedPayload`, implemented in the base as CKAN discovery plus a cached GET; parsing then runs as `_parse(path, locator, provenance, options)`. A reader for another source subclasses `BaseGovDataReader[ItsLocator]`, overrides `locator_type()`, and overrides `_fetch`. For offline reruns, `DownloadCache.get_or_download(url, revalidate=False)` reads the cached body without issuing a request and raises `CacheMissError` on a miss.

`_fetch(locator, client)` never receives `Options`, so a source that needs credentials from `Options.context` (see `DestatisReader`) overrides `_read_table(locator, options)` instead, building its own client and calling `_parse` directly.

To connect a new dataset:

1. Check whether `GovDataReader` already handles it. A GovData slug or a direct CSV URL with a regular single-row header needs no code; every column is read as a string. For typed columns, subclass `GovDataReader` in a new module and set `schema` (see `population.py`).
2. For a different payload shape, subclass `BaseGovDataReader[GovDataLocator]` and implement `_parse` (and `suffix` for non-CSV payloads); `bundeswahlleiterin.py` and `uba.py` show the pattern. For a different source, also override `locator_type()` and `_fetch`.
3. Keep source-specific parse logic in the source's module as a `parse_*_bytes` function plus a path wrapper, like `uba.py`. Generic parsing belongs in `core/parse.py`. That keeps it testable from fixture files without network access.
4. Add tests under `mloda_plugin_govdata/feature_groups/govdata/tests/` with a small real sample in `tests/fixtures/`, and record its source and license in the `NOTICE` there.
5. Export the reader from `feature_groups/govdata/__init__.py` and add a usage snippet to the README.
6. Run `tox` (pytest, ruff, mypy strict, bandit); it must pass before a PR.
