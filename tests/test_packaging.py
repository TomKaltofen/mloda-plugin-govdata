"""Packaging config: the wheel ships code only, and a mloda override cannot drift from the dependency."""

import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path
from typing import cast

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = REPO_ROOT / "mloda_plugin_govdata"


def _find_config() -> dict[str, list[str]]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    return cast(dict[str, list[str]], data["tool"]["setuptools"]["packages"]["find"])


def _dotted(path: Path) -> str:
    return ".".join(path.relative_to(REPO_ROOT).parts)


def _mloda(requirements: list[str]) -> list[str]:
    return [req for req in requirements if re.match(r"mloda\s*[<>=!~]", req)]


def test_tests_packages_are_excluded_from_the_wheel() -> None:
    # Same fnmatch semantics setuptools applies to include and exclude patterns.
    find = _find_config()
    tests_dirs = [path for path in DISTRIBUTION.rglob("tests") if path.is_dir()]
    assert tests_dirs, "no tests package under the distribution"
    candidates = list(tests_dirs) + [path for tests_dir in tests_dirs for path in tests_dir.rglob("*") if path.is_dir()]
    shipped = sorted(
        _dotted(path)
        for path in candidates
        if any(fnmatchcase(_dotted(path), pattern) for pattern in find["include"])
        and not any(fnmatchcase(_dotted(path), pattern) for pattern in find["exclude"])
    )
    assert shipped == []


def test_no_package_data_is_shipped() -> None:
    # A stale egg-info manifest would otherwise re-add excluded test modules as package data.
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert data["tool"]["setuptools"]["include-package-data"] is False


def test_a_mloda_override_matches_the_mloda_dependency() -> None:
    # A uv override replaces the project's own requirement too, so a drifted one would win silently.
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    overrides = _mloda(data["tool"]["uv"].get("override-dependencies", []))
    assert overrides in ([], _mloda(data["project"]["dependencies"]))
