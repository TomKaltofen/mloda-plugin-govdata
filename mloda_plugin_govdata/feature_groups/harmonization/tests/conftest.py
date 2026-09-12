"""Offline fixtures: the captured GENESIS replies behind a mocked POST, the reference extracts behind the loaders."""

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx

from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE
from mloda_plugin_govdata.feature_groups.destatis.reader import DestatisReader
from mloda_plugin_govdata.feature_groups.harmonization.nuts import AgsToNutsFeature
from mloda_plugin_govdata.feature_groups.harmonization.rebase import KreisRebaseFeature
from mloda_plugin_govdata.harmonization.edition import Edition
from mloda_plugin_govdata.harmonization.reference.bbsr import parse_bbsr_kreise_workbook
from mloda_plugin_govdata.harmonization.reference.eurostat import parse_lau_nuts_de_workbook
from mloda_plugin_govdata.harmonization.reference.gv_isys import parse_gv_isys_workbook
from mloda_plugin_govdata.harmonization.reference.sources import BBSR_KREISE, ReferenceSource

_PACKAGE = Path(__file__).resolve().parents[3]
TOKEN = "test-token"
GOETTINGEN_ZIP = "12411-0015_2013-2017_de_flat.zip"
COCHEM_ZELL_ZIP = "12411-0015_2013-2014_de_flat.zip"
LAND_ZIP = "12411-0010_2024_de_flat.zip"
GOETTINGEN_LOCATOR = {
    "name": "12411-0015",
    "regionalvariable": "KREISE",
    "regionalkey": ["03152", "03156", "03159"],
    "startyear": 2013,
    "endyear": 2017,
}

# The fixture is an extract, so its edition names the extract's own hash (see the reference NOTICE).
EXTRACT = ReferenceSource(
    name="BBSR Umsteigeschluessel Kreise (test extract)",
    url=BBSR_KREISE.url,
    sha256="5784d7da0cffc2f0643529531bafa34a764753202955c3b35dbf5335a3e47fb0",
    license=BBSR_KREISE.license,
    attribution=BBSR_KREISE.attribution,
)


@pytest.fixture
def ffcsv_fixtures_dir() -> Path:
    return _PACKAGE / "feature_groups" / "destatis" / "tests" / "fixtures" / "ffcsv"


@pytest.fixture
def reference_fixtures_dir() -> Path:
    return _PACKAGE / "harmonization" / "reference" / "tests" / "fixtures"


@pytest.fixture
def expected_dir() -> Path:
    return _PACKAGE / "harmonization" / "tests" / "fixtures"


@pytest.fixture
def govdata_fixtures_dir() -> Path:
    return _PACKAGE / "feature_groups" / "govdata" / "tests" / "fixtures"


@pytest.fixture
def genesis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ffcsv_fixtures_dir: Path) -> Callable[[str], respx.Route]:
    """Isolated reader cache plus an env token; returns a mocker for the tablefile POST."""
    monkeypatch.setattr(DestatisReader, "cache_dir", str(tmp_path))
    monkeypatch.setenv("GENESIS_TOKEN", TOKEN)

    def mock(zip_name: str) -> respx.Route:
        zip_bytes = (ffcsv_fixtures_dir / zip_name).read_bytes()
        return respx.post(GENESIS_ONLINE.base_url + "data/tablefile").mock(
            return_value=httpx.Response(200, content=zip_bytes, headers={"content-type": "application/octet-stream"})
        )

    return mock


@pytest.fixture
def extract_keys(monkeypatch: pytest.MonkeyPatch, reference_fixtures_dir: Path) -> None:
    rows = parse_bbsr_kreise_workbook(reference_fixtures_dir / "bbsr-ref-kreise-extract.xlsx")
    monkeypatch.setattr(KreisRebaseFeature, "load_keys", classmethod(lambda cls: (rows, EXTRACT)))


def fixture_edition(reference_fixtures_dir: Path, *, with_history: bool = True) -> Edition:
    lau_rows = tuple(parse_lau_nuts_de_workbook(reference_fixtures_dir / "eurostat-lau-nuts-de-extract.xlsx"))
    changes = tuple(parse_gv_isys_workbook(reference_fixtures_dir / "gv-isys-2016-extract.xlsx"))
    return Edition(
        gebietsstand="2024",
        nuts_version="2024",
        source="test extract",
        url="test://lau-nuts",
        sha256=None,
        year_range=(2016, 2024),
        lau_rows=lau_rows,
        gv_isys_changes=changes if with_history else (),
    )


@pytest.fixture
def extract_edition(monkeypatch: pytest.MonkeyPatch, reference_fixtures_dir: Path) -> Edition:
    edition = fixture_edition(reference_fixtures_dir)
    monkeypatch.setattr(AgsToNutsFeature, "edition", classmethod(lambda cls: edition))
    return edition
