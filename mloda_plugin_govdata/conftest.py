"""Shared pytest fixtures for every ``tests/`` package under ``mloda_plugin_govdata``."""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir(request: pytest.FixtureRequest) -> Path:
    return Path(request.path).parent / "fixtures"
