from pathlib import Path

import pytest


@pytest.fixture
def reference_fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "reference" / "tests" / "fixtures"
