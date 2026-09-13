"""The wheel ships code only: the packages.find exclude patterns cover every tests package."""

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


def test_tests_packages_are_excluded_from_the_wheel() -> None:
    # Same fnmatch semantics setuptools applies to include and exclude patterns.
    find = _find_config()
    tests_dirs = [path for path in DISTRIBUTION.rglob("tests") if path.is_dir()]
    assert tests_dirs, "no tests package under the distribution"
    candidates = [tests_dir for tests_dir in tests_dirs] + [
        path for tests_dir in tests_dirs for path in tests_dir.rglob("*") if path.is_dir()
    ]
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
