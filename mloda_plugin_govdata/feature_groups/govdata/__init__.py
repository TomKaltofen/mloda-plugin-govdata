"""GovData connector: read German open-government CSV distributions into mloda."""

from .discovery import Dataset, ResolvedDistribution, Resource, normalize_license, resolve_distribution
from .locator import GovDataLocator
from .parse import ColumnType, parse_german_csv, parse_german_csv_bytes, parse_multi_header_csv
from .reader import BundeswahlleiterinReader, GovDataFeature, GovDataReader, UbaAirReader
from .uba import UBA_AIR_BASE, parse_uba_measures, parse_uba_measures_bytes, uba_measures_url

__all__ = [
    "UBA_AIR_BASE",
    "BundeswahlleiterinReader",
    "ColumnType",
    "Dataset",
    "GovDataFeature",
    "GovDataLocator",
    "GovDataReader",
    "Resource",
    "ResolvedDistribution",
    "UbaAirReader",
    "normalize_license",
    "parse_german_csv",
    "parse_german_csv_bytes",
    "parse_multi_header_csv",
    "parse_uba_measures",
    "parse_uba_measures_bytes",
    "resolve_distribution",
    "uba_measures_url",
]
