"""capture_genesis_fixtures.py: argument parsing, redaction, and the live-host call, mocked."""

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
import respx

from mloda_plugin_govdata.feature_groups.destatis.core.api import GenesisClient
from mloda_plugin_govdata.feature_groups.destatis.core.auth import ENV_SUFFIXES
from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE, KNOWN_HOSTS
from mloda_plugin_govdata.feature_groups.destatis.core.redact import REDACTED
from scripts.capture_genesis_fixtures import _parse_pairs, _write, capture, main

_CREDENTIAL_ENV_VARS = tuple(host.env_var(suffix) for host in KNOWN_HOSTS.values() for suffix in ENV_SUFFIXES)


@pytest.fixture(autouse=True)
def _instant_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mloda_plugin_govdata.feature_groups.govdata.core.client._BASE_WAIT", lambda _state: 0.0)


def _client(tmp_path: Path) -> GenesisClient:
    return GenesisClient(GENESIS_ONLINE, None, lock_dir=tmp_path, environ={})


# --- argument parsing --------------------------------------------------------------------------


def test_parse_pairs_builds_a_dict() -> None:
    assert _parse_pairs(["name=12411-0015", "format=ffcsv"]) == {"name": "12411-0015", "format": "ffcsv"}


@pytest.mark.parametrize("pair", ["badpair", "=ffcsv"])
def test_parse_pairs_rejects_a_malformed_pair(pair: str) -> None:
    with pytest.raises(SystemExit, match="--tablefile expects key=value"):
        _parse_pairs([pair])


def test_unknown_host_choice_is_rejected_by_argparse(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--host", "not-a-host", "--out", str(tmp_path)])
    assert excinfo.value.code == 2


def test_missing_out_is_rejected_by_argparse() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2


@respx.mock
def test_no_credentials_and_not_guest_exits_with_a_clear_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # respx with no routes registered: any accidental request past this early return raises
    # instead of silently reaching the network.
    for var in _CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    assert main(["--out", str(tmp_path)]) == 2
    assert "no credentials for genesis" in capsys.readouterr().err


# --- _write: the redaction safety net ----------------------------------------------------------


def test_write_returns_the_sha256_when_no_secret_survives(tmp_path: Path) -> None:
    data = b'{"ok": true}'
    sha = _write(tmp_path, "fixture.json", data, ["sub-token"])
    assert sha == hashlib.sha256(data).hexdigest()
    assert (tmp_path / "fixture.json").read_bytes() == data


def test_write_with_no_secrets_never_flags_anything(tmp_path: Path) -> None:
    # --guest mode: secrets is empty, so the safety net is vacuously off.
    data = b"anything at all, even a fake secret-looking string"
    sha = _write(tmp_path, "fixture.txt", data, [])
    assert sha == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "variant",
    [
        "p ss+w/rd",  # the plain secret, as sent
        quote("p ss+w/rd", safe=""),  # fully URL-encoded (%20/%2B/%2F), as it can appear on the wire
    ],
)
def test_write_fails_loudly_and_deletes_the_file_if_a_secret_variant_survives(tmp_path: Path, variant: str) -> None:
    data = f"leaked: {variant}".encode()
    with pytest.raises(SystemExit, match="redaction failed"):
        _write(tmp_path, "fixture.txt", data, ["p ss+w/rd"])
    assert not (tmp_path / "fixture.txt").exists()


# --- capture: body branches, over a mocked host -----------------------------------------------


@respx.mock
def test_capture_redacts_a_json_body_before_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    respx.get(GENESIS_ONLINE.base_url + "helloworld/whoami").mock(
        return_value=httpx.Response(200, json={"User-Agent": "sub-token"})
    )
    with _client(tmp_path) as client:
        capture(client, "helloworld/whoami", {}, tmp_path, "whoami", ["sub-token"])
    assert json.loads((tmp_path / "whoami.json").read_text(encoding="utf-8")) == {"User-Agent": REDACTED}
    assert "whoami.json: HTTP 200, json" in capsys.readouterr().out


@respx.mock
def test_capture_redacts_a_text_body_before_writing(tmp_path: Path) -> None:
    respx.get(GENESIS_ONLINE.base_url + "helloworld/whoami").mock(
        return_value=httpx.Response(
            200, content=b"plain text with sub-token inside", headers={"content-type": "text/plain"}
        )
    )
    with _client(tmp_path) as client:
        capture(client, "helloworld/whoami", {}, tmp_path, "whoami", ["sub-token"])
    written = (tmp_path / "whoami.txt").read_text(encoding="utf-8")
    assert written == f"plain text with {REDACTED} inside"


@respx.mock
def test_capture_fails_loudly_when_a_secret_survives_in_the_unredacted_zip_body(tmp_path: Path) -> None:
    # The zip branch skips redact_json/redact_text; _write's post-hoc literal-byte scan is the
    # sole guard here, and only sees stored/uncompressed bytes, not a secret inside a real
    # deflated GENESIS zip payload (a known, separate limitation, not covered by this test).
    body = b"PK\x03\x04" + b"leaked sub-token inside the archive bytes"
    respx.get(GENESIS_ONLINE.base_url + "helloworld/whoami").mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "application/octet-stream"})
    )
    with _client(tmp_path) as client, pytest.raises(SystemExit, match="redaction failed"):
        capture(client, "helloworld/whoami", {}, tmp_path, "whoami", ["sub-token"])
    assert not (tmp_path / "whoami.zip").exists()
    assert not (tmp_path / "NOTICE").exists()


@respx.mock
def test_capture_does_not_write_on_a_redirect(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Credentials are not sent across redirects (a stale base URL); nothing is captured either.
    respx.get(GENESIS_ONLINE.base_url + "helloworld/whoami").mock(
        return_value=httpx.Response(307, headers={"location": "https://example.org/"})
    )
    with _client(tmp_path) as client:
        capture(client, "helloworld/whoami", {}, tmp_path, "whoami", ["sub-token"])
    assert not any(path.suffix != ".lock" for path in tmp_path.iterdir())
    assert "not captured" in capsys.readouterr().out
