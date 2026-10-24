"""Credentials: resolution order, host scoping, redaction in every text form, the missing-credentials message."""

from typing import Any

import pytest
from mloda.user import Credential, DataAccessCollection, Options

from mloda_plugin_govdata.feature_groups.destatis.core.auth import (
    ENV_SUFFIXES,
    OPTION_GENESIS_CREDENTIALS,
    DestatisCredentials,
    credentials_from_collection,
    explicit_credentials_from_options,
    resolve_credentials,
)
from mloda_plugin_govdata.feature_groups.destatis.core.errors import MissingCredentialsError, WrongHostCredentialsError
from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE, REGIONALSTATISTIK, GenesisHost

TOKEN = "t0kenAbCdEf0123456789abcdef012345"
USER = "someone@example.org"
PASSWORD = "p4ss w0rd?&="


def test_token_credentials_normalize_and_send_token_as_username() -> None:
    credentials = DestatisCredentials(host=" genesis ", token=f"  {TOKEN}\n")
    assert credentials.host == "genesis"
    assert credentials.headers() == {"username": TOKEN, "password": ""}
    assert not credentials.has_password_path


def test_password_credentials_need_both_parts() -> None:
    credentials = DestatisCredentials(user=USER, password=PASSWORD)
    assert credentials.headers() == {"username": USER, "password": PASSWORD}
    assert credentials.has_password_path
    with pytest.raises(ValueError, match="together"):
        DestatisCredentials(user=USER)
    with pytest.raises(ValueError, match="token or user"):
        DestatisCredentials()


def test_repr_and_str_redact() -> None:
    credentials = DestatisCredentials(token=TOKEN, user=USER, password=PASSWORD)
    for text in (repr(credentials), str(credentials), f"{credentials}"):
        assert TOKEN not in text and USER not in text and PASSWORD not in text
        assert "<redacted>" in text
    assert credentials.secrets() == (TOKEN, USER, PASSWORD)


def test_options_context_never_prints_the_secret() -> None:
    credentials = DestatisCredentials(token=TOKEN)
    options = Options(group={"DestatisReader": "12411-0015"}, context={OPTION_GENESIS_CREDENTIALS: credentials})
    assert TOKEN not in str(options) and TOKEN not in repr(options)
    assert explicit_credentials_from_options(options) is credentials
    # The context does not feed the hash: two features with different credentials batch together.
    other = Options(
        group={"DestatisReader": "12411-0015"}, context={OPTION_GENESIS_CREDENTIALS: DestatisCredentials(token="x")}
    )
    assert hash(options) == hash(other)


def test_options_group_is_refused() -> None:
    options = Options(group={OPTION_GENESIS_CREDENTIALS: DestatisCredentials(token=TOKEN)})
    with pytest.raises(ValueError, match="context"):
        explicit_credentials_from_options(options)


def test_options_context_refuses_anything_but_the_redacting_instance() -> None:
    # Only the redacting instance: a plain mapping's masking would depend on mloda's key-name heuristics.
    options = Options(context={OPTION_GENESIS_CREDENTIALS: {"token": TOKEN}})
    with pytest.raises(TypeError, match="DestatisCredentials instance"):
        explicit_credentials_from_options(options)
    with pytest.raises(TypeError):
        explicit_credentials_from_options(Options(context={OPTION_GENESIS_CREDENTIALS: 42}))


def test_control_characters_and_non_latin1_are_refused_without_echo() -> None:
    for bad in (f"{TOKEN}\nX-Injected: 1", "tok\x00en", "töken☃"):
        with pytest.raises(ValueError) as info:
            DestatisCredentials(token=bad)
        assert "token" in str(info.value) and bad not in str(info.value)
    with pytest.raises(ValueError, match="password"):
        DestatisCredentials(user=USER, password="p\rw")


def test_env_resolution_is_host_prefixed() -> None:
    environ = {"GENESIS_TOKEN": TOKEN, "REGIONALSTATISTIK_USER": USER, "REGIONALSTATISTIK_PASSWORD": PASSWORD}
    genesis = resolve_credentials(GENESIS_ONLINE, environ=environ)
    regional = resolve_credentials(REGIONALSTATISTIK, environ=environ)
    assert genesis.headers()["username"] == TOKEN and genesis.host == "genesis"
    assert regional.headers() == {"username": USER, "password": PASSWORD} and regional.host == "regionalstatistik"


def test_env_never_falls_back_to_the_other_host() -> None:
    with pytest.raises(MissingCredentialsError) as info:
        resolve_credentials(REGIONALSTATISTIK, environ={"GENESIS_TOKEN": TOKEN})
    message = str(info.value)
    for suffix in ENV_SUFFIXES:
        assert f"REGIONALSTATISTIK_{suffix}" in message
    assert REGIONALSTATISTIK.registration_url in message
    assert "free" in message and "same-day" in message
    assert TOKEN not in message


def test_env_half_password_path_is_an_error_naming_the_missing_var() -> None:
    with pytest.raises(MissingCredentialsError, match="GENESIS_PASSWORD"):
        resolve_credentials(GENESIS_ONLINE, environ={"GENESIS_USER": USER})


def test_env_half_password_path_is_an_error_even_with_a_token() -> None:
    with pytest.raises(MissingCredentialsError, match="GENESIS_PASSWORD") as info:
        resolve_credentials(GENESIS_ONLINE, environ={"GENESIS_TOKEN": TOKEN, "GENESIS_USER": USER})
    assert TOKEN not in str(info.value)


def test_explicit_credentials_win_over_env_and_must_match_the_host() -> None:
    explicit = DestatisCredentials(host="genesis", token=TOKEN)
    assert resolve_credentials(GENESIS_ONLINE, explicit, environ={"GENESIS_TOKEN": "other"}) is explicit
    with pytest.raises(WrongHostCredentialsError, match="separate per host"):
        resolve_credentials(REGIONALSTATISTIK, explicit, environ={})


def test_env_whitespace_is_normalized() -> None:
    credentials = resolve_credentials(GENESIS_ONLINE, environ={"GENESIS_TOKEN": f" {TOKEN} \t"})
    assert credentials.headers()["username"] == TOKEN


def test_explicit_credentials_from_options_is_none_without_a_context_entry() -> None:
    assert explicit_credentials_from_options(None) is None
    assert explicit_credentials_from_options(Options({"DestatisReader": "12411-0015"})) is None


def test_explicit_credentials_from_options_never_touches_env_or_a_host() -> None:
    # A cache-hit caller (peek) must be able to build this before deciding whether a request
    # happens at all, so this never resolves from the environment and takes no host argument.
    credentials = DestatisCredentials(token=TOKEN)
    options = Options(context={OPTION_GENESIS_CREDENTIALS: credentials})
    assert explicit_credentials_from_options(options) is credentials


def test_unknown_host_with_explicit_prefix() -> None:
    zensus = GenesisHost(
        "zensus", "https://example.org/rest/2020", "ZENSUS", "https://example.org/", "Zensus (example)"
    )
    assert zensus.base_url.endswith("/")
    assert resolve_credentials(zensus, environ={"ZENSUS_TOKEN": TOKEN}).host == "zensus"
    with pytest.raises(ValueError, match="upper-case"):
        GenesisHost("x", "https://example.org/", "zensus", "https://example.org/", "x")


def _collection(**credentials: Any) -> DataAccessCollection:
    return DataAccessCollection(credentials={handle: Credential(entry) for handle, entry in credentials.items()})


def test_collection_credentials_are_picked_by_host_handle_or_host_key() -> None:
    collection = _collection(
        genesis={"token": TOKEN}, nrw={"host": "regionalstatistik", "user": USER, "password": PASSWORD}
    )
    online = credentials_from_collection(collection, GENESIS_ONLINE)
    assert online is not None and (online.host, online.token) == ("genesis", TOKEN)
    regional = credentials_from_collection(collection, REGIONALSTATISTIK)
    assert regional is not None and (regional.host, regional.user) == ("regionalstatistik", USER)
    assert credentials_from_collection(None, GENESIS_ONLINE) is None


@pytest.mark.parametrize(
    "entry",
    [
        {"token": TOKEN},  # another plugin's token under its own handle
        {"host": "db.example.org", "user": USER, "password": PASSWORD},  # a database login
    ],
)
def test_untagged_collection_credentials_are_never_taken(entry: dict[str, str]) -> None:
    assert credentials_from_collection(_collection(other=entry), GENESIS_ONLINE) is None


def test_a_data_access_handle_selects_among_several() -> None:
    collection = _collection(work={"host": "genesis", "token": TOKEN}, home={"host": "genesis", "token": "other"})
    with pytest.raises(ValueError, match="Several credentials for host 'genesis': home, work; .*data_access_handle"):
        credentials_from_collection(collection, GENESIS_ONLINE)
    picked = credentials_from_collection(collection, GENESIS_ONLINE, "work")
    assert picked is not None and picked.token == TOKEN
    # A handle of another kind or group is not ours to judge.
    assert credentials_from_collection(_collection(genesis={"token": TOKEN}), GENESIS_ONLINE, "files") is not None
    with pytest.raises(WrongHostCredentialsError, match="'work' are scoped to host 'genesis'"):
        credentials_from_collection(collection, REGIONALSTATISTIK, "work")


def test_a_handle_never_reaches_past_the_genesis_tag() -> None:
    collection = _collection(regionalstatistik={"token": TOKEN}, hf={"token": "foreign"}, genesis={"token": "online"})
    # A host-named handle keeps its own host: never sent to the other installation.
    with pytest.raises(WrongHostCredentialsError, match="'regionalstatistik' are scoped to host 'regionalstatistik'"):
        credentials_from_collection(collection, GENESIS_ONLINE, "regionalstatistik")
    # A handle naming another plugin's entry is left to that plugin; the tagged entry is used.
    picked = credentials_from_collection(collection, GENESIS_ONLINE, "hf")
    assert picked is not None and picked.token == "online"
    tagged = credentials_from_collection(
        _collection(nrw={"host": " Regionalstatistik ", "token": TOKEN}), REGIONALSTATISTIK
    )
    assert tagged is not None and tagged.host == "regionalstatistik"


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        ({"tokn": TOKEN}, r"'genesis' have unknown key\(s\) \['tokn'\]"),
        ({"user": USER}, "'genesis': .*together"),
    ],
)
def test_a_malformed_genesis_entry_is_named_without_its_values(entry: dict[str, str], match: str) -> None:
    with pytest.raises(ValueError, match=match) as excinfo:
        credentials_from_collection(_collection(genesis=entry), GENESIS_ONLINE)
    assert TOKEN not in str(excinfo.value) and USER not in str(excinfo.value)
