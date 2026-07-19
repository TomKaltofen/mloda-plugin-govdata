"""Every marimo demo must define its app without running any cell (no network)."""

import importlib.util
from pathlib import Path

import pytest

# A hard import on purpose: tox installs the demo extra, so a broken marimo
# dependency set must fail this test instead of skipping it.
import marimo

DEMO_PATHS = sorted((Path(__file__).resolve().parents[1] / "demos").glob("*.py"))


def test_demo_glob_finds_all_demos() -> None:
    # A silently empty glob must fail, not skip the suite.
    assert len(DEMO_PATHS) >= 2


@pytest.mark.parametrize("demo_path", DEMO_PATHS, ids=lambda path: path.stem)
def test_demo_defines_marimo_app(demo_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(demo_path.stem, demo_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert isinstance(module.app, marimo.App)
