"""Contract test: every operation the client implements against the pinned OpenAPI specs (request side only)."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from mloda_plugin_govdata.feature_groups.destatis.core.api import OPERATIONS, Operation
from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE, REGIONALSTATISTIK

SPEC_PREFIX = "/rest/2020/"
SPECS = {
    GENESIS_ONLINE.name: (
        "GOJsonApi-2026-08-16.json",
        "1a0dc57a85e391b6c7c42de4120156f92a8b0f6a6e10d3e51b8be59536c1e8e6",
    ),
    REGIONALSTATISTIK.name: (
        "GOJsonApi-regionalstatistik-2026-08-16.json",
        "a9ce7944d21fc1a9f5330790d9dff939748320486bfb40eadc82608000cd684c",
    ),
}
# Defaults the client relies on: ffcsv is always sent explicitly, quality stays off unless asked,
# job is never true, language is pinned, area is left to the server.
TABLEFILE_DEFAULTS = {"format": "datencsv", "quality": "off", "job": "false", "language": "de", "area": "free"}
# Request-side differences between the two hosts' specs, all outside the client's surface.
KNOWN_HOST_DIFFERENCES = {
    ("/rest/2020/data/chart2table", "post"),
    ("/rest/2020/data/table", "post"),
    ("/rest/2020/profile/password", "get"),
    ("/rest/2020/profile/removeResult", "get"),
}


def _load(fixtures_dir: Path, host: str) -> dict[str, Any]:
    name, sha = SPECS[host]
    raw = (fixtures_dir / "openapi" / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha, f"{name} changed; re-pin deliberately (see NOTICE)"
    spec: dict[str, Any] = json.loads(raw)
    return spec


def _spec_operation(spec: dict[str, Any], operation: Operation) -> dict[str, Any]:
    path = spec["paths"].get(SPEC_PREFIX + operation.path)
    assert path is not None, f"{operation.path} is not a path in the spec (case matters)"
    method = path.get(operation.method.lower())
    assert method is not None, f"{operation.path} does not declare {operation.method}"
    result: dict[str, Any] = method
    return result


def _header_params(op: dict[str, Any]) -> set[str]:
    return {p["name"] for p in op.get("parameters", []) if p.get("in") == "header"}


def _query_params(op: dict[str, Any]) -> set[str]:
    return {p["name"] for p in op.get("parameters", []) if p.get("in") == "query"}


def _form_fields(op: dict[str, Any]) -> dict[str, Any]:
    content = op.get("requestBody", {}).get("content", {})
    assert set(content) <= {"application/x-www-form-urlencoded"}, "the client only speaks form encoding"
    fields: dict[str, Any] = {}
    for body in content.values():
        fields.update(body.get("schema", {}).get("properties", {}))
    return fields


@pytest.mark.parametrize("host", sorted(SPECS))
def test_operations_match_spec(fixtures_dir: Path, host: str) -> None:
    spec = _load(fixtures_dir, host)
    for endpoint, operation in OPERATIONS.items():
        assert endpoint == operation.path
        op = _spec_operation(spec, operation)
        headers = _header_params(op)
        if operation.credentials:
            assert headers >= {"username", "password"}, f"{endpoint}: credential headers not declared"
        else:
            assert not headers & {"username", "password"}, f"{endpoint}: unexpected credential headers"
        if operation.method == "GET":
            assert not op.get("requestBody"), f"{endpoint}: GET with a request body"
            declared = _query_params(op)
        else:
            declared = set(_form_fields(op))
        undeclared = operation.fields - declared
        assert not undeclared, f"{endpoint}: client may send fields the spec does not declare: {sorted(undeclared)}"


@pytest.mark.parametrize("host", sorted(SPECS))
def test_tablefile_defaults(fixtures_dir: Path, host: str) -> None:
    fields = _form_fields(_spec_operation(_load(fixtures_dir, host), OPERATIONS["data/tablefile"]))
    assert len(fields) == 25
    for name, default in TABLEFILE_DEFAULTS.items():
        assert fields[name].get("default") == default, f"{name} default moved; revisit the wire policy"


@pytest.mark.parametrize("host", sorted(SPECS))
def test_logincheck_and_qualitysigns_language(fixtures_dir: Path, host: str) -> None:
    spec = _load(fixtures_dir, host)
    logincheck = _form_fields(_spec_operation(spec, OPERATIONS["helloworld/logincheck"]))
    assert logincheck["language"].get("default") == "de"
    qualitysigns_get = _spec_operation(spec, OPERATIONS["catalogue/qualitysigns"])
    assert _query_params(qualitysigns_get) == {"language"}
    # The POST variant exists too; the client uses GET (no credentials on either).
    assert "post" in spec["paths"][SPEC_PREFIX + "catalogue/qualitysigns"]


def _request_side(spec: dict[str, Any]) -> dict[tuple[str, str], Any]:
    side: dict[tuple[str, str], Any] = {}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            params = sorted(
                (p["name"], p.get("in"), p.get("schema", {}).get("default")) for p in op.get("parameters", [])
            )
            fields = {name: prop.get("default") for name, prop in _form_fields(op).items()}
            side[(path, method)] = (params, fields)
    return side


def test_hosts_agree_on_request_side_except_known_differences(fixtures_dir: Path) -> None:
    genesis = _request_side(_load(fixtures_dir, GENESIS_ONLINE.name))
    regional = _request_side(_load(fixtures_dir, REGIONALSTATISTIK.name))
    differing = {key for key in genesis.keys() | regional.keys() if genesis.get(key) != regional.get(key)}
    assert differing == KNOWN_HOST_DIFFERENCES
    assert not {(SPEC_PREFIX + op.path, op.method.lower()) for op in OPERATIONS.values()} & differing
