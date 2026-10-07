"""The marimo demos must define their apps without running any cell (no network)."""

import ast
import importlib.util
from pathlib import Path
from typing import TypeGuard

# A hard import on purpose: tox installs the demo extra, so a broken marimo
# dependency set must fail this test instead of skipping it.
import marimo
import pytest

DEMO_PATH = Path(__file__).resolve().parents[1] / "demos" / "govdata_demo.py"
RECIPES_DIR = DEMO_PATH.parents[1] / "recipes"
DEMO_PATHS = sorted(DEMO_PATH.parent.glob("*.py"))


def test_demo_glob_finds_all_demos() -> None:
    # A silently empty glob must fail, not skip the parametrized tests.
    assert DEMO_PATH in DEMO_PATHS and len(DEMO_PATHS) >= 2


@pytest.mark.parametrize("demo_path", DEMO_PATHS, ids=lambda path: path.stem)
def test_demo_defines_marimo_app(demo_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(demo_path.stem, demo_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert isinstance(module.app, marimo.App)


@pytest.mark.parametrize("demo_path", DEMO_PATHS, ids=lambda path: path.stem)
def test_every_plugin_name_a_demo_imports_exists(demo_path: Path) -> None:
    # Cell bodies never run here, so a moved module or a renamed export only shows up this way.
    imports = [
        node
        for node in ast.walk(_demo_tree(demo_path))
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("mloda_plugin_govdata")
    ]
    assert imports
    missing = [
        f"{node.module}.{alias.name}"
        for node in imports
        for alias in node.names
        if not hasattr(importlib.import_module(str(node.module)), alias.name)
    ]
    assert missing == []


def _demo_tree(path: Path = DEMO_PATH) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


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


def _is_cell(node: ast.stmt) -> TypeGuard[ast.FunctionDef]:
    # ``@app.cell`` or, once code is hidden in the editor, ``@app.cell(hide_code=True)``.
    return isinstance(node, ast.FunctionDef) and any(
        ast.unparse(d.func if isinstance(d, ast.Call) else d) == "app.cell" for d in node.decorator_list
    )


def _is_markdown(cell: ast.FunctionDef) -> bool:
    body = [stmt for stmt in cell.body if not isinstance(stmt, ast.Return)]
    return (
        len(body) == 1
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Call)
        and ast.unparse(body[0].value.func) == "mo.md"
    )


def test_every_cell_after_the_credentials_guard_depends_on_it() -> None:
    # mo.stop skips only the cells that take a name from the stopped cell, directly or through another cell.
    cells = [node for node in _demo_tree().body if _is_cell(node)]
    guard = next(index for index, cell in enumerate(cells) if "mo.stop(" in ast.unparse(cell))
    reached = _returned_names(cells[guard])
    guarded: list[int] = []
    unguarded: list[int] = []
    for cell in cells[guard + 1 :]:
        if _is_markdown(cell):
            continue  # shown even without credentials
        if {arg.arg for arg in cell.args.args} & reached:
            guarded.append(cell.lineno)
            reached |= _returned_names(cell)
        else:
            unguarded.append(cell.lineno)
    assert guarded, "the Destatis cells follow the guard"
    assert unguarded == []
