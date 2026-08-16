"""Source-neutral provenance of a fetched payload: where it came from and under which license."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .discovery import Dataset, ResolvedDistribution


@dataclass(frozen=True)
class Provenance:
    """Where a payload came from; ``dataset`` carries the CKAN record when discovery ran."""

    source: str  # access path label: "ckan", "url"
    url: str  # distribution URL or API endpoint
    parameters: Mapping[str, str] = field(default_factory=dict)  # request parameters, empty for a plain GET
    license: str | None = None
    dataset: Dataset | None = None

    @classmethod
    def from_distribution(cls, distribution: ResolvedDistribution) -> Provenance:
        """``ckan`` when discovery ran, ``url`` for a direct distribution."""
        return cls(
            source="ckan" if distribution.dataset is not None else "url",
            url=distribution.url,
            license=distribution.license,
            dataset=distribution.dataset,
        )


@dataclass(frozen=True)
class FetchedPayload:
    """A payload on disk; ``sha256`` is over the stored bytes."""

    path: Path
    sha256: str
    retrieved_at: datetime
    provenance: Provenance
