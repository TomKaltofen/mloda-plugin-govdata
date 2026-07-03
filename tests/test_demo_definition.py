"""The marimo demo must define its app without running any cell (no network)."""

import importlib.util
from pathlib import Path

import pytest

DEMO_PATH = Path(__file__).resolve().parents[1] / "demos" / "govdata_demo.py"


def test_demo_defines_marimo_app() -> None:
    marimo = pytest.importorskip("marimo")
    spec = importlib.util.spec_from_file_location("govdata_demo", DEMO_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert isinstance(module.app, marimo.App)
