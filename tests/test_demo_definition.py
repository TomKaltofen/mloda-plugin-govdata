"""The marimo demo must define its app without running any cell (no network)."""

import ast
import importlib.util
from pathlib import Path

# A hard import on purpose: tox installs the demo extra, so a broken marimo
# dependency set must fail this test instead of skipping it.
import marimo

DEMO_PATH = Path(__file__).resolve().parents[1] / "demos" / "govdata_demo.py"
RECIPES_DIR = DEMO_PATH.parents[1] / "recipes"


def test_demo_defines_marimo_app() -> None:
    spec = importlib.util.spec_from_file_location("govdata_demo", DEMO_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert isinstance(module.app, marimo.App)


def test_every_recipe_file_the_demo_names_is_shipped() -> None:
    tree = ast.parse(DEMO_PATH.read_text(encoding="utf-8"))
    names = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".json")
    }
    assert names, "the Destatis chapter loads recipe files"
    assert all((RECIPES_DIR / name).is_file() for name in names), names
