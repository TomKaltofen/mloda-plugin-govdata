"""CKAN discovery: resolve a GovData dataset to a distribution URL and license."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from .client import request_with_retry
from .locator import GovDataLocator

# dcat-ap.de license URIs observed across GovData distributions -> short labels.
LICENSE_LABELS: dict[str, str] = {
    "http://dcat-ap.de/def/licenses/cc-by/4.0": "CC-BY-4.0",
    "http://dcat-ap.de/def/licenses/dl-by-de/2.0": "DL-DE-BY-2.0",
    "http://dcat-ap.de/def/licenses/dl-zero-de/2.0": "DL-DE-Zero-2.0",
    "http://dcat-ap.de/def/licenses/cc-zero": "CC0-1.0",
    "http://dcat-ap.de/def/licenses/geonutz/20130319": "GeoNutzV",
}


def normalize_license(uri: str | None) -> str | None:
    """Map a dcat-ap.de license URI to a short label, tolerating spelling drift.

    Returns the raw value for unknown / free-text licenses (warn, never refuse),
    and None when no license is present.
    """
    if not uri:
        return None
    candidate = uri.strip()
    # dataset-level uses dl-by-de/2_0, resource-level dl-by-de/2.0; normalize the underscore.
    normalized = candidate.replace("/2_0", "/2.0")
    return LICENSE_LABELS.get(candidate) or LICENSE_LABELS.get(normalized) or candidate


class Resource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    format: str | None = None
    license: str | None = None
    mimetype: str | None = None
    name: str | None = None
    size: int | None = None


class Dataset(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    title: str | None = None
    notes: str | None = None
    resources: list[Resource] = []
    extras: dict[str, str] = {}

    @classmethod
    def from_ckan(cls, result: dict[str, Any]) -> "Dataset":
        extras = {e["key"]: str(e.get("value", "")) for e in result.get("extras", []) if "key" in e}
        resources = [Resource.model_validate(r) for r in result.get("resources", [])]
        return cls(
            name=result.get("name"),
            title=result.get("title"),
            notes=result.get("notes"),
            resources=resources,
            extras=extras,
        )


@dataclass(frozen=True)
class ResolvedDistribution:
    url: str
    license: str | None
    dataset: Dataset | None


def fetch_dataset(client: httpx.Client, locator: GovDataLocator) -> Dataset:
    """Call CKAN ``package_show`` for the locator's dataset id."""
    response = request_with_retry(
        client,
        "GET",
        f"{locator.ckan_base}/package_show",
        params={"id": locator.dataset_id},
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    if not payload.get("success"):
        raise ValueError(f"CKAN package_show was not successful for {locator.dataset_id!r}")
    return Dataset.from_ckan(payload["result"])


def _looks_like_csv(resource: Resource) -> bool:
    """True when the resource advertises CSV via format, mimetype, or URL suffix."""
    fmt = (resource.format or "").strip().lower()
    mimetype = (resource.mimetype or "").strip().lower()
    return fmt == "csv" or mimetype == "text/csv" or resource.url.lower().endswith(".csv")


def _select_resource(resources: list[Resource], resource_index: int) -> Resource:
    """Pick the distribution to read, preferring CSV since that is all the reader parses."""
    if not 0 <= resource_index < len(resources):
        raise IndexError(f"resource_index {resource_index} is out of range ({len(resources)} resources)")
    chosen = resources[resource_index]
    if _looks_like_csv(chosen):
        return chosen
    for resource in resources:
        if _looks_like_csv(resource):
            return resource
    return chosen


def resolve_distribution(locator: GovDataLocator, client: httpx.Client) -> ResolvedDistribution:
    """Resolve a locator to a concrete distribution URL plus its license.

    A direct ``distribution_url`` is used as-is; a ``dataset_id`` is resolved via
    ``package_show``, reading the license from the chosen distribution (the
    distribution ``license`` is reliably populated; dataset ``license_id`` is not).
    """
    if locator.distribution_url is not None:
        return ResolvedDistribution(url=locator.distribution_url, license=None, dataset=None)

    dataset = fetch_dataset(client, locator)
    if not dataset.resources:
        raise ValueError(f"dataset {locator.dataset_id!r} exposes no resources")
    resource = _select_resource(dataset.resources, locator.resource_index)
    return ResolvedDistribution(url=resource.url, license=normalize_license(resource.license), dataset=dataset)
