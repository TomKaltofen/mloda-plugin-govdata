"""Level 1: Provenance construction from a resolved distribution."""

import typing

from mloda_plugin_govdata.feature_groups.govdata.core.discovery import Dataset, ResolvedDistribution
from mloda_plugin_govdata.feature_groups.govdata.core.provenance import FetchedPayload, Provenance


def test_from_distribution() -> None:
    dataset = Dataset(name="x")
    with_dataset = ResolvedDistribution(url="https://example.org/data.csv", license="CC-BY-4.0", dataset=dataset)
    provenance = Provenance.from_distribution(with_dataset)
    assert provenance.source == "ckan"
    assert provenance.license == "CC-BY-4.0"
    assert provenance.dataset is dataset
    assert provenance.parameters == {}

    without_dataset = ResolvedDistribution(url="https://example.org/data.csv", license=None, dataset=None)
    assert Provenance.from_distribution(without_dataset).source == "url"


def test_annotations_resolve_at_runtime() -> None:
    assert typing.get_type_hints(Provenance)["dataset"] == Dataset | None
    assert typing.get_type_hints(FetchedPayload)["provenance"] is Provenance
