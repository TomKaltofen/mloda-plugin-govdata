from pathlib import Path

import pytest

_FEATURE_GROUPS = Path(__file__).parents[2] / "feature_groups"


@pytest.fixture
def reference_fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "reference" / "tests" / "fixtures"


@pytest.fixture
def ffcsv_fixtures_dir() -> Path:
    return _FEATURE_GROUPS / "destatis" / "tests" / "fixtures" / "ffcsv"


@pytest.fixture
def govdata_fixtures_dir() -> Path:
    return _FEATURE_GROUPS / "govdata" / "tests" / "fixtures"
