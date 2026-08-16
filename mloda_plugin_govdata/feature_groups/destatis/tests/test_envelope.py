"""Reply shapes and the status-to-exception mapping, pinned to the captured and documented fixtures."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from mloda_plugin_govdata.feature_groups.destatis.core.envelope import (
    CODE_RESULT_TOO_LARGE,
    CODE_TABLE_NOT_FOUND,
    GenesisEnvelope,
    GenesisStatus,
    HelloWorldReply,
    LoginCheckReply,
    inspect_response,
    parse_json_reply,
    raise_for_logincheck,
    raise_for_status_block,
)
from mloda_plugin_govdata.feature_groups.destatis.core.errors import (
    GenesisAuthError,
    GenesisBackendError,
    GenesisEmptySelection,
    GenesisJobAccepted,
    GenesisMaintenance,
    GenesisResultTooLarge,
    GenesisUnknownEnvelope,
    GenesisUnknownTable,
)


def _json(fixtures_dir: Path, name: str) -> Any:
    return json.loads((fixtures_dir / name).read_text(encoding="utf-8"))


def _response(status: int, body: bytes, content_type: str) -> httpx.Response:
    return httpx.Response(status, content=body, headers={"content-type": content_type})


def test_qualitysigns_envelope_strips_credentials_from_parameter(fixtures_dir: Path) -> None:
    reply = parse_json_reply(_json(fixtures_dir, "genesis-guest-qualitysigns.json"))
    assert isinstance(reply, GenesisEnvelope)
    assert reply.ident is not None and (reply.ident.service, reply.ident.method) == ("catalogue", "qualitysigns")
    assert reply.status.code == 0 and not reply.status.is_error
    assert reply.parameter == {"language": "de"}
    assert reply.entries is not None and [row["Code"] for row in reply.entries] == [
        "0",
        "-",
        "...",
        "/",
        ".",
        "x",
        "()",
        "p",
        "r",
        "s",
    ]
    assert reply.data is None and reply.copyright is not None
    raise_for_status_block(reply.status)  # code 0 passes


def test_regionalstatistik_qualitysigns_has_the_same_legend(fixtures_dir: Path) -> None:
    genesis = parse_json_reply(_json(fixtures_dir, "genesis-guest-qualitysigns.json"))
    regional = parse_json_reply(_json(fixtures_dir, "regionalstatistik-guest-qualitysigns.json"))
    assert isinstance(genesis, GenesisEnvelope) and isinstance(regional, GenesisEnvelope)
    assert genesis.entries == regional.entries


def test_whoami_is_flat(fixtures_dir: Path) -> None:
    reply = parse_json_reply(_json(fixtures_dir, "genesis-guest-whoami.json"))
    assert isinstance(reply, HelloWorldReply)
    assert reply.user_agent.startswith("mloda-plugin-govdata/")


def test_logincheck_success_needs_a_real_username(fixtures_dir: Path) -> None:
    ok = parse_json_reply(_json(fixtures_dir, "documented-logincheck-ok.json"))
    assert isinstance(ok, LoginCheckReply) and ok.is_success and not ok.is_guest
    raise_for_logincheck(ok)
    guest = parse_json_reply(_json(fixtures_dir, "regionalstatistik-guest-logincheck.json"))
    assert isinstance(guest, LoginCheckReply) and guest.is_guest and not guest.is_success
    with pytest.raises(GenesisAuthError, match="GAST"):
        raise_for_logincheck(guest)
    for blank in (
        {"Status": ok.status},
        {"Status": ok.status, "Username": "  "},
        {"Status": ok.status, "Username": None},
    ):
        nameless = LoginCheckReply.model_validate(blank)
        assert not nameless.is_success
        with pytest.raises(GenesisAuthError, match="without a username"):
            raise_for_logincheck(nameless)


def test_validation_failure_is_a_genesis_error_without_the_values() -> None:
    with pytest.raises(GenesisUnknownEnvelope) as info:
        parse_json_reply({"Status": {"Code": "not-a-number", "Content": "SECRET-ECHO"}})
    assert "GenesisEnvelope" in str(info.value) and "Status.Code" in str(info.value)
    assert "SECRET-ECHO" not in str(info.value) and "not-a-number" not in str(info.value)
    with pytest.raises(GenesisUnknownEnvelope, match="Parameter"):
        parse_json_reply({"Status": {"Code": 0}, "Parameter": "username=SECRET"})


def test_logincheck_repr_redacts_the_echo() -> None:
    reply = LoginCheckReply.model_validate({"Status": "ok", "Username": "secret-token"})
    assert "secret-token" not in repr(reply) and "secret-token" not in str(reply)
    assert "GAST" in repr(LoginCheckReply.model_validate({"Status": "ok", "Username": "GAST"}))


def test_logincheck_bad_credentials_and_backend_error(fixtures_dir: Path) -> None:
    bad = parse_json_reply(_json(fixtures_dir, "regionalstatistik-badcreds-logincheck.json"))
    assert isinstance(bad, LoginCheckReply)
    with pytest.raises(GenesisAuthError, match="rejected"):
        raise_for_logincheck(bad)
    degraded = parse_json_reply(_json(fixtures_dir, "genesis-guest-logincheck.json"))
    assert isinstance(degraded, LoginCheckReply)
    with pytest.raises(GenesisBackendError, match="web UI"):
        raise_for_logincheck(degraded)


def test_logincheck_unknown_text_raises() -> None:
    with pytest.raises(GenesisUnknownEnvelope):
        raise_for_logincheck(LoginCheckReply.model_validate({"Status": "Something new", "Username": "someone"}))


def test_flat_status_shapes_from_fixtures(fixtures_dir: Path) -> None:
    not_authorized = parse_json_reply(_json(fixtures_dir, "regionalstatistik-guest-metadata-table-13211-02-05-4.json"))
    assert isinstance(not_authorized, GenesisStatus) and not_authorized.code == 15 and not_authorized.is_error
    with pytest.raises(GenesisAuthError):
        raise_for_status_block(not_authorized, http_status=401)
    wrong = parse_json_reply(_json(fixtures_dir, "regionalstatistik-badcreds-tablefile-13211-02-05-4.json"))
    assert isinstance(wrong, GenesisStatus) and wrong.code == 2
    with pytest.raises(GenesisAuthError):
        raise_for_status_block(wrong, http_status=404)
    degraded = parse_json_reply(_json(fixtures_dir, "genesis-guest-metadata-table-12411-0015.json"))
    assert isinstance(degraded, GenesisStatus) and degraded.code == 2
    with pytest.raises(GenesisBackendError):
        raise_for_status_block(degraded, http_status=404)


def test_documented_no_objects_maps_to_empty_selection(fixtures_dir: Path) -> None:
    reply = parse_json_reply(_json(fixtures_dir, "documented-tablefile-no-objects.json"))
    assert isinstance(reply, GenesisEnvelope) and reply.data is None
    assert "username" not in reply.parameter and reply.parameter["name"] == "12411-0001"
    with pytest.raises(GenesisEmptySelection) as info:
        raise_for_status_block(reply.status, http_status=200, endpoint="data/tablefile")
    assert info.value.status_block == {"Code": 104, "Content": reply.status.content, "Type": "Information"}
    assert info.value.endpoint == "data/tablefile" and info.value.http_status == 200


def _status(code: int, content: str, type_: str = "Information") -> GenesisStatus:
    return GenesisStatus.model_validate({"Code": code, "Content": content, "Type": type_})


# Synthetic status blocks: these codes are recorded by pystatis, not captured here yet (see fixtures/NOTICE).
def test_synthetic_codes_map_to_typed_exceptions() -> None:
    with pytest.raises(GenesisResultTooLarge):
        raise_for_status_block(_status(CODE_RESULT_TOO_LARGE, "irrelevant"))
    with pytest.raises(GenesisResultTooLarge):
        raise_for_status_block(_status(1, "Die Tabelle ist zu groß"))
    with pytest.raises(GenesisUnknownTable):
        raise_for_status_block(_status(CODE_TABLE_NOT_FOUND, "Die angeforderte Tabelle ist nicht vorhanden"))
    with pytest.raises(GenesisJobAccepted):
        raise_for_status_block(_status(99, "Der Bearbeitungsauftrag wurde erstellt. ...: 12411-0015_001"))


def test_warning_passes_and_type_is_case_insensitive() -> None:
    raise_for_status_block(_status(22, "erfolgreich (Mindestens ein Parameter ...)", "Warnung"))
    assert _status(0, "x", "ERROR").is_error and _status(0, "x", "Fehler").is_error
    assert _status(22, "x", "WARNING").is_warning
    # The too-large text heuristic never overrides a documented pass.
    raise_for_status_block(_status(22, "erfolgreich (Auswahl zu groß, angepasst)", "Warnung"))
    raise_for_status_block(_status(0, "zu groß steht hier nur im Text"))


def test_unknown_status_quotes_the_block() -> None:
    with pytest.raises(GenesisUnknownEnvelope, match="'Code': 4711"):
        raise_for_status_block(_status(4711, "Neu", "Information"), http_status=200)
    with pytest.raises(GenesisUnknownEnvelope):
        raise_for_status_block(_status(0, "x", "Error"))


def test_parse_rejects_unknown_shapes() -> None:
    with pytest.raises(GenesisUnknownEnvelope, match="keys"):
        parse_json_reply({"Foo": 1})
    with pytest.raises(GenesisUnknownEnvelope, match="not a JSON object"):
        parse_json_reply([1, 2])


def test_inspect_zip_json_html_and_garbage(fixtures_dir: Path) -> None:
    zipped = inspect_response(_response(200, b"PK\x03\x04rest", "application/octet-stream"), "data/tablefile")
    assert zipped.kind == "zip" and zipped.reply is None and zipped.body.startswith(b"PK")
    assert "PK" not in repr(zipped)  # the body stays out of reprs (a logincheck body echoes the username)
    with pytest.raises(GenesisUnknownEnvelope, match="HTTP 403"):
        inspect_response(_response(403, b"PK\x03\x04rest", "application/octet-stream"), "data/tablefile")
    ok = inspect_response(_response(200, (fixtures_dir / "genesis-guest-whoami.json").read_bytes(), "application/json"))
    assert ok.kind == "json" and isinstance(ok.reply, HelloWorldReply)
    with pytest.raises(GenesisMaintenance, match="HTML"):
        inspect_response(_response(503, (fixtures_dir / "synthetic-maintenance.html").read_bytes(), "text/html"))
    with pytest.raises(GenesisMaintenance):
        inspect_response(_response(200, b"  <html>no content type</html>", ""))
    with pytest.raises(GenesisUnknownEnvelope, match="neither"):
        inspect_response(_response(200, b"plain text", "text/plain"))


def test_inspect_maps_http_error_bodies(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "regionalstatistik-guest-metadata-table-13211-02-05-4.json").read_bytes()
    with pytest.raises(GenesisAuthError) as info:
        inspect_response(_response(401, body, "application/json"), "metadata/table")
    assert info.value.http_status == 401 and info.value.endpoint == "metadata/table"
    with pytest.raises(GenesisUnknownEnvelope, match="HTTP 418"):
        inspect_response(_response(418, b'{"User-Agent": "x"}', "application/json"))
