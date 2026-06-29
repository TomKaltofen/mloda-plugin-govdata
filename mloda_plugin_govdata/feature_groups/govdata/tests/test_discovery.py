"""Level 1/2: CKAN discovery, metadata model, and license resolution."""

import json
from pathlib import Path

import httpx
import respx

from mloda_plugin_govdata.feature_groups.govdata.client import build_client
from mloda_plugin_govdata.feature_groups.govdata.discovery import (
    Dataset,
    Resource,
    _select_resource,
    normalize_license,
    resolve_distribution,
)
from mloda_plugin_govdata.feature_groups.govdata.locator import GovDataLocator

PACKAGE_SHOW = "https://ckan.govdata.de/api/3/action/package_show"
SLUG = "einwohner-nach-altersgruppen-und-stadtbezirken"


def test_normalize_license_known_and_free_text() -> None:
    assert normalize_license("http://dcat-ap.de/def/licenses/cc-by/4.0") == "CC-BY-4.0"
    # dataset-level spelling drift (underscore) normalizes to the resource-level label.
    assert normalize_license("http://dcat-ap.de/def/licenses/dl-by-de/2_0") == "DL-DE-BY-2.0"
    assert normalize_license("Es gelten keine Zugriffsbeschränkungen") == "Es gelten keine Zugriffsbeschränkungen"
    assert normalize_license(None) is None


def test_dataset_from_ckan_fixture(fixtures_dir: Path) -> None:
    payload = json.loads((fixtures_dir / "package_show.json").read_text(encoding="utf-8"))
    dataset = Dataset.from_ckan(payload["result"])
    assert dataset.name == SLUG
    assert dataset.resources[0].license == "http://dcat-ap.de/def/licenses/cc-by/4.0"
    assert dataset.resources[0].format == "CSV"
    assert "modified" in dataset.extras  # DCAT freshness extra is preserved


@respx.mock
def test_resolve_distribution_reads_license_from_distribution(fixtures_dir: Path) -> None:
    payload = (fixtures_dir / "package_show.json").read_text(encoding="utf-8")
    route = respx.get(PACKAGE_SHOW).mock(return_value=httpx.Response(200, text=payload))
    with build_client() as client:
        resolved = resolve_distribution(GovDataLocator(dataset_id=SLUG), client)
    assert route.called
    assert resolved.license == "CC-BY-4.0"
    assert resolved.url.endswith(".csv")


def test_resolve_direct_url_skips_discovery() -> None:
    with build_client() as client:
        resolved = resolve_distribution(GovDataLocator(distribution_url="https://example.org/data.csv"), client)
    assert resolved.url == "https://example.org/data.csv"
    assert resolved.license is None


def test_select_resource_prefers_csv_over_first_non_csv() -> None:
    resources = [
        Resource(url="https://example.org/page.html", format="HTML"),
        Resource(url="https://example.org/data.csv", format="CSV"),
    ]
    assert _select_resource(resources, 0).url.endswith(".csv")
