"""mloda reader and FeatureGroup for GovData distributions.

``GovDataReader`` follows the ``CsvReader`` pattern (a ``ReadFile`` subclass):
it resolves a locator to a distribution, downloads it through the cache, and
parses it into a typed Arrow table. ``GovDataFeature`` exposes it as a root
FeatureGroup on the PyArrow compute framework.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, ClassVar

import pyarrow as pa

from mloda.provider import BaseInputData, FeatureSet

# Imported for its registration side effect so "PyArrowTable" resolves; the reader returns a pyarrow Table.
from mloda_plugins.compute_framework.base_implementations.pyarrow.table import PyArrowTable  # noqa: F401
from mloda_plugins.feature_group.input_data.read_file import ReadFile
from mloda_plugins.feature_group.input_data.read_file_feature import ReadFileFeature

from .cache import DownloadCache
from .client import build_client
from .discovery import ResolvedDistribution, resolve_distribution
from .locator import GovDataLocator
from .parse import ColumnType, parse_german_csv, parse_multi_header_csv
from .uba import parse_uba_measures

# The M1 population dataset (Stuttgart, via GovData) and its known typed schema.
POPULATION_SLUG = "einwohner-nach-altersgruppen-und-stadtbezirken"
POPULATION_URL_MARKER = "einwohner-in-stuttgart-nach-altersgruppen"
POPULATION_SCHEMA: dict[str, ColumnType] = {
    "Stichtag": ColumnType.DATE,
    "Stadtbezirk": ColumnType.STRING,
    "Alter in 10 Gruppen": ColumnType.STRING,
    "Einwohner": ColumnType.INTEGER,
}


class GovDataReader(ReadFile):
    """Reads a GovData CSV distribution into a typed Arrow table."""

    # Persistent, content-addressed cache location (override per environment).
    cache_dir: ClassVar[str] = str(Path(tempfile.gettempdir()) / "mloda-govdata-cache")

    @classmethod
    def suffix(cls) -> tuple[str, ...]:
        return (".csv",)

    @classmethod
    def match_subclass_data_access(cls, data_access: Any, feature_names: list[str], options: Any) -> Any:
        return GovDataLocator.coerce(data_access)

    @classmethod
    def load_data(cls, data_access: Any, features: FeatureSet) -> Any:
        # Touch features first: the framework probes load_data(None, None) and
        # only tolerates AttributeError to detect scoped-access support.
        requested = sorted(features.get_all_names())  # deterministic column order
        locator = GovDataLocator.coerce(data_access)
        if locator is None:
            raise ValueError(f"GovDataReader cannot handle data access {data_access!r}")
        table = cls._read_table(locator)
        return table.select(requested)

    @classmethod
    def _read_table(cls, locator: GovDataLocator) -> pa.Table:
        with build_client() as client:
            distribution = resolve_distribution(locator, client)
            cache = DownloadCache(cls.cache_dir, client=client)
            cached = cache.get_or_download(distribution.url)
            return cls._parse(cached.path, locator, distribution)

    @classmethod
    def _parse(cls, path: Path, locator: GovDataLocator, distribution: ResolvedDistribution) -> pa.Table:
        return parse_german_csv(path, cls._schema_for(locator, distribution))

    @staticmethod
    def _schema_for(locator: GovDataLocator, distribution: ResolvedDistribution) -> dict[str, ColumnType] | None:
        if locator.dataset_id == POPULATION_SLUG or POPULATION_URL_MARKER in distribution.url:
            return POPULATION_SCHEMA
        return None  # unknown dataset: read every column as a string


class BundeswahlleiterinReader(GovDataReader):
    """Reads the Bundeswahlleiterin kerg.csv result file (5-line preamble, 3-row merged header)."""

    @classmethod
    def _parse(cls, path: Path, locator: GovDataLocator, distribution: ResolvedDistribution) -> pa.Table:
        return parse_multi_header_csv(path, skiprows=5, header_rows=3, label_columns=4, value_type=ColumnType.INTEGER)


class UbaAirReader(GovDataReader):
    """Reads the UBA Air Data v4 ``measures`` JSON endpoint into a typed Arrow table.

    The option value is a full ``measures`` URL (build one with
    :func:`~mloda_plugin_govdata.feature_groups.govdata.uba.uba_measures_url`); the response
    is flattened to one row per station and measurement timestamp. Reuses the client, cache,
    retry, and direct-URL resolution; only the parse seam differs from the CSV readers.
    """

    @classmethod
    def suffix(cls) -> tuple[str, ...]:
        return (".json",)

    @classmethod
    def _parse(cls, path: Path, locator: GovDataLocator, distribution: ResolvedDistribution) -> pa.Table:
        return parse_uba_measures(path)


class GovDataFeature(ReadFileFeature):
    """Root FeatureGroup for GovData columns; inherits the any-framework rule to avoid resolver collisions."""

    @classmethod
    def input_data(cls) -> BaseInputData | None:
        return GovDataReader()
