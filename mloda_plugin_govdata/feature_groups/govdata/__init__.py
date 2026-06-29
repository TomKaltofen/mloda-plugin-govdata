"""GovData connector: read German open-government CSV distributions into mloda."""

from .discovery import Dataset, ResolvedDistribution, Resource, normalize_license, resolve_distribution
from .locator import GovDataLocator
from .parse import ColumnType, parse_german_csv, parse_german_csv_bytes, parse_multi_header_csv
from .reader import BundeswahlleiterinReader, GovDataFeature, GovDataReader

__all__ = [
    "BundeswahlleiterinReader",
    "ColumnType",
    "Dataset",
    "GovDataFeature",
    "GovDataLocator",
    "GovDataReader",
    "Resource",
    "ResolvedDistribution",
    "normalize_license",
    "parse_german_csv",
    "parse_german_csv_bytes",
    "parse_multi_header_csv",
    "resolve_distribution",
]
