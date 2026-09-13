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


def _recipe_files_the_demo_loads() -> set[str]:
    tree = ast.parse(DEMO_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "load_recipe"
    ]
    return {
        leaf.value
        for call in calls
        for leaf in ast.walk(call)
        if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str)
    }


def test_every_recipe_file_the_demo_loads_is_shipped() -> None:
    names = _recipe_files_the_demo_loads()
    assert names, "the Destatis chapter loads recipe files"
    assert [name for name in sorted(names) if not (RECIPES_DIR / name).is_file()] == []
