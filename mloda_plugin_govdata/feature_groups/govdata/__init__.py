"""GovData connector: read German open-government data into mloda."""

from .bundeswahlleiterin import (
    OPTION_WAHL_HEADER_ROWS,
    OPTION_WAHL_LABEL_COLUMNS,
    OPTION_WAHL_SKIPROWS,
    OPTION_WAHL_VALUE_TYPE,
    BundeswahlleiterinReader,
)
from .core.cache import CacheMissError, DownloadCache
from .core.client import build_client
from .core.discovery import (
    Dataset,
    ResolvedDistribution,
    Resource,
    normalize_license,
    resolve_distribution,
    search_datasets,
)
from .core.locator import GovDataLocator, Locator
from .core.parse import ColumnType, parse_german_csv, parse_german_csv_bytes, parse_multi_header_csv
from .core.provenance import FetchedPayload, Provenance
from .feature import GovDataFeature
from .population import POPULATION_SCHEMA, POPULATION_SLUG, StuttgartPopulationReader
from .reader import BaseGovDataReader, GovDataReader
from .uba import UBA_AIR_BASE, UbaAirReader, parse_uba_measures, parse_uba_measures_bytes, uba_measures_url

__all__ = [
    "OPTION_WAHL_HEADER_ROWS",
    "OPTION_WAHL_LABEL_COLUMNS",
    "OPTION_WAHL_SKIPROWS",
    "OPTION_WAHL_VALUE_TYPE",
    "POPULATION_SCHEMA",
    "POPULATION_SLUG",
    "UBA_AIR_BASE",
    "BaseGovDataReader",
    "BundeswahlleiterinReader",
    "CacheMissError",
    "ColumnType",
    "Dataset",
    "DownloadCache",
    "FetchedPayload",
    "GovDataFeature",
    "GovDataLocator",
    "GovDataReader",
    "Locator",
    "Provenance",
    "ResolvedDistribution",
    "Resource",
    "StuttgartPopulationReader",
    "UbaAirReader",
    "build_client",
    "normalize_license",
    "parse_german_csv",
    "parse_german_csv_bytes",
    "parse_multi_header_csv",
    "parse_uba_measures",
    "parse_uba_measures_bytes",
    "resolve_distribution",
    "search_datasets",
    "uba_measures_url",
]
