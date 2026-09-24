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


def _demo_tree() -> ast.Module:
    return ast.parse(DEMO_PATH.read_text(encoding="utf-8"))


def _recipe_files_the_demo_loads() -> set[str]:
    calls = [
        node
        for node in ast.walk(_demo_tree())
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
    assert names, "the recipe chapters load recipe files"
    assert [name for name in sorted(names) if not (RECIPES_DIR / name).is_file()] == []


def _returned_names(cell: ast.FunctionDef) -> set[str]:
    last = cell.body[-1]
    if not isinstance(last, ast.Return) or last.value is None:
        return set()
    values = last.value.elts if isinstance(last.value, ast.Tuple) else [last.value]
    return {value.id for value in values if isinstance(value, ast.Name)}


def test_every_destatis_cell_waits_for_the_credentials_guard() -> None:
    # mo.stop skips only the cells that take a name from the stopped cell, directly or through another cell.
    cells = [
        node
        for node in _demo_tree().body
        if isinstance(node, ast.FunctionDef) and any(ast.unparse(d) == "app.cell" for d in node.decorator_list)
    ]
    guard = next(index for index, cell in enumerate(cells) if "mo.stop(" in ast.unparse(cell))
    reached = _returned_names(cells[guard])
    unguarded = []
    for cell in cells[guard + 1 :]:
        params = {arg.arg for arg in cell.args.args}
        if params == {"mo"}:
            continue  # markdown, shown even without credentials
        if params & reached:
            reached |= _returned_names(cell)
        else:
            unguarded.append(cell.lineno)
    assert unguarded == []
