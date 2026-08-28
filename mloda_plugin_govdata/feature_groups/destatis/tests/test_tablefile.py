"""tablefile_parameters (M2 wire policy) and fetch_tablefile (the zip-kind check)."""

import inspect
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from mloda_plugin_govdata.feature_groups.destatis.core.api import (
    GENESIS_ONLINE,
    TABLEFILE_FIELDS,
    GenesisClient,
    fetch_tablefile,
    tablefile_parameters,
)
from mloda_plugin_govdata.feature_groups.destatis.core.auth import DestatisCredentials
from mloda_plugin_govdata.feature_groups.destatis.core.cache import ParameterCache
from mloda_plugin_govdata.feature_groups.destatis.core.errors import GenesisUnknownEnvelope

BASE = GENESIS_ONLINE.base_url
TOKEN = "t0kenAbCdEf0123456789abcdef012345"
ZIP_BODY = b"PK\x03\x04" + b"\x00" * 16 + b"ffcsv-payload"

NOT_CALLER_CONFIGURABLE = {"area", "compress", "transpose", "timeslices", "job", "stand"}
NEVER_SENT = {"area", "stand", "timeslices"}


def _client(tmp_path: Path) -> GenesisClient:
    return GenesisClient(GENESIS_ONLINE, DestatisCredentials(token=TOKEN), lock_dir=tmp_path, environ={})


def test_minimal_selection_sends_only_the_pinned_fields() -> None:
    assert tablefile_parameters("12411-0015") == {
        "name": "12411-0015",
        "language": "de",
        "format": "ffcsv",
        "job": "false",
        "compress": "false",
        "transpose": "false",
        "quality": "off",
    }


def test_full_selection_field_set_and_wire_policy() -> None:
    fields = tablefile_parameters(
        "12411-0015",
        regionalvariable="DLAND",
        regionalkey=["02", "01"],
        classifyingvariable1="GES",
        classifyingkey1=["W", "M"],
        classifyingvariable2="ALT",
        classifyingkey2="U18",
        classifyingvariable3="X3",
        classifyingkey3="k3",
        classifyingvariable4="X4",
        classifyingkey4="k4",
        classifyingvariable5="X5",
        classifyingkey5="k5",
        contents=["BEVSTD"],
        startyear=2015,
        endyear=2022,
        quality=True,
    )
    assert set(fields) == {
        "name",
        "regionalvariable",
        "regionalkey",
        "classifyingvariable1",
        "classifyingkey1",
        "classifyingvariable2",
        "classifyingkey2",
        "classifyingvariable3",
        "classifyingkey3",
        "classifyingvariable4",
        "classifyingkey4",
        "classifyingvariable5",
        "classifyingkey5",
        "contents",
        "startyear",
        "endyear",
        "language",
        "format",
        "job",
        "compress",
        "transpose",
        "quality",
    }
    assert set(fields) <= TABLEFILE_FIELDS  # never a name outside the spec's tablefile body
    assert fields["quality"] == "on"
    assert fields["language"] == "de"
    assert fields["format"] == "ffcsv"
    assert NEVER_SENT.isdisjoint(fields)
    assert fields["compress"] == "false"
    assert fields["transpose"] == "false"
    assert fields["job"] == "false"


def test_non_german_language_is_rejected() -> None:
    # parse_ffcsv_bytes assumes German decimal-comma formatting; an "en" reply (dot decimals, same
    # column names) would pass the layout guard and silently corrupt every value if allowed through.
    with pytest.raises(ValueError, match="language must be 'de'"):
        tablefile_parameters("12411-0015", language="en")


def test_area_compress_transpose_timeslices_job_stand_are_not_parameters() -> None:
    # Not locator fields in M2 (docs/destatis-options.md): there is no way to send anything but the
    # pinned wire value for them through this function.
    assert NOT_CALLER_CONFIGURABLE.isdisjoint(inspect.signature(tablefile_parameters).parameters)


@respx.mock
def test_fetch_tablefile_returns_the_zip_body(tmp_path: Path) -> None:
    respx.post(BASE + "data/tablefile").mock(
        return_value=httpx.Response(200, content=ZIP_BODY, headers={"content-type": "application/octet-stream"})
    )
    with _client(tmp_path) as client:
        body = fetch_tablefile(client, {"name": "12411-0015", "format": "ffcsv", "language": "de"})
    assert body == ZIP_BODY


@respx.mock
def test_fetch_tablefile_raises_on_a_non_zip_reply(tmp_path: Path) -> None:
    respx.post(BASE + "data/tablefile").mock(
        return_value=httpx.Response(
            200,
            json={
                "Ident": {"Service": "data", "Method": "tablefile"},
                "Status": {"Code": 0, "Content": "erfolgreich", "Type": "Information"},
            },
        )
    )
    with _client(tmp_path) as client, pytest.raises(GenesisUnknownEnvelope, match="did not answer with a zip"):
        fetch_tablefile(client, {"name": "12411-0015", "format": "ffcsv", "language": "de"})


@respx.mock
def test_tablefile_parameters_round_trip_through_parameter_cache(tmp_path: Path) -> None:
    # The intended composition: tablefile_parameters builds `fields`, ParameterCache.get_or_fetch
    # canonicalizes them and calls `fetch` (fetch_tablefile bound to a client) only on a miss.
    route = respx.post(BASE + "data/tablefile").mock(
        return_value=httpx.Response(200, content=ZIP_BODY, headers={"content-type": "application/octet-stream"})
    )
    fields = tablefile_parameters("12411-0015", regionalkey=["02", "01"], quality=True)
    cache = ParameterCache(tmp_path / "cache")
    with _client(tmp_path) as client:
        fetch = partial(fetch_tablefile, client)
        cached = cache.get_or_fetch(GENESIS_ONLINE, "data/tablefile", fields, fetch)
        cache.get_or_fetch(GENESIS_ONLINE, "data/tablefile", fields, fetch)  # cache hit, no second POST
    assert cached.path.read_bytes() == ZIP_BODY
    assert route.calls.call_count == 1
    sent = parse_qs(route.calls.last.request.content.decode("utf-8"))
    assert sent["regionalkey"] == ["01,02"]  # canonicalized: sorted, comma-joined
    assert sent["quality"] == ["on"]
