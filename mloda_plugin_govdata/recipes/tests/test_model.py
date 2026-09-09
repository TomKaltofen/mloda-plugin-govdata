"""Recipe model: file shape, unknown keys, compliance fields, and credential rejection."""

import dataclasses
import json
from typing import Any

import pytest

from mloda_plugin_govdata.recipes import (
    TOKEN_RUN_LENGTH,
    FeatureItem,
    Recipe,
    RecipeError,
    environment_secrets,
    parse_recipe,
)

LOCATOR = {"name": "12411-0010", "startyear": 2024, "endyear": 2024}
SOURCE: dict[str, Any] = {
    "license": "dl-de/by-2-0",
    "attribution": "(c) Statistisches Bundesamt (Destatis), 2026",
    "dataset_uri": "https://genesis.destatis.de/datenbank/online/statistic/12411/table/12411-0010",
    "retrieved_at": "2026-09-08T00:00:00Z",
    "sha256": "aba0f99e3b8eef1f4d975c0e2ed3d7323024dd8a798dbd875e35ae34447f3916",
    "modifications": [],
    "credential_env": ["GENESIS_TOKEN"],
}
# Built, not pasted, so no token-shaped literal sits in the source tree.
TOKEN_LIKE = "t0ken" + "Ab1" * 8
GENESIS_ENV = ("GENESIS_TOKEN", "GENESIS_USER", "GENESIS_PASSWORD")


def _recipe(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "features": [{"name": "value", "options": {"DestatisReader": dict(LOCATOR)}}],
        "links": [],
        "compliance": {"sources": [dict(SOURCE)]},
    }
    document.update(overrides)
    return document


def _source(**overrides: Any) -> dict[str, Any]:
    source = dict(SOURCE)
    source.update(overrides)
    return source


def _rejects(document: dict[str, Any], match: str) -> RecipeError:
    with pytest.raises(RecipeError, match=match) as excinfo:
        parse_recipe(json.dumps(document))
    return excinfo.value


@pytest.fixture(autouse=True)
def _no_genesis_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in GENESIS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_feature_item_fields_mirror_mloda_feature_config() -> None:
    from mloda.core.api.feature_config.models import FeatureConfig

    assert set(FeatureItem.model_fields) == {f.name for f in dataclasses.fields(FeatureConfig)}


def test_minimal_recipe_validates_and_links_default_to_empty() -> None:
    recipe = Recipe.model_validate(_recipe(links=None) | {"links": []})
    assert recipe.links == []
    assert recipe.features == [{"name": "value", "options": {"DestatisReader": LOCATOR}}]
    recipe = Recipe.model_validate({"features": ["value"], "compliance": {"sources": [SOURCE]}})
    assert recipe.links == []


def test_a_top_level_unknown_key_is_rejected() -> None:
    _rejects(_recipe(notes="census break"), "notes: Extra inputs are not permitted")


def test_features_must_be_a_non_empty_array() -> None:
    _rejects(_recipe(features=[]), "features: List should have at least 1 item")
    _rejects(_recipe(features={"name": "value"}), "features")


def test_an_unknown_key_inside_a_feature_item_names_it_and_the_allowed_keys() -> None:
    error = _rejects(_recipe(features=[{"name": "value", "bogus": 1}]), r"features\[0\]: unknown key\(s\) \['bogus'\]")
    assert "'column_index', 'context_options', 'feature_group', 'group_options', 'in_features', 'name'" in str(error)


def test_feature_item_types_are_checked() -> None:
    _rejects(_recipe(features=[{"name": "value", "in_features": "a"}]), r"features\[0\]: in_features: Input should be")


def test_empty_feature_names_are_rejected() -> None:
    _rejects(_recipe(features=[""]), r"features\[0\]: a feature name must not be empty")
    _rejects(_recipe(features=[{"name": ""}]), r"features\[0\]: name: String should have at least 1 character")


def test_compliance_is_required_with_at_least_one_source() -> None:
    document = _recipe()
    del document["compliance"]
    _rejects(document, "compliance: Field required")
    _rejects(_recipe(compliance={"sources": []}), "compliance.sources: List should have at least 1 item")


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("sha256", "ABA0F99E", "64 lower-case hex digits"),
        ("sha256", "g" * 64, "64 lower-case hex digits"),
        ("retrieved_at", "2026-09-08T00:00:00", "timezone"),
        ("retrieved_at", "yesterday", "retrieved_at"),
        ("dataset_uri", "genesis.destatis.de/12411-0010", "URI with a scheme"),
        ("license", "", "at least 1 character"),
        ("credential_env", ["genesis_token"], "env-var names only"),
        ("credential_env", ["GENESIS TOKEN"], "env-var names only"),
        ("credential_env", "GENESIS_TOKEN", "credential_env"),
    ],
)
def test_source_compliance_fields_are_validated(field: str, value: Any, match: str) -> None:
    _rejects(_recipe(compliance={"sources": [_source(**{field: value})]}), match)


def test_link_join_must_be_a_supported_type() -> None:
    side = {"feature_group": "GovDataFeature", "index": ["Nr"]}
    link = {"join": "asof", "left": side, "right": side}
    _rejects(
        _recipe(links=[link]), "links.0.join: Input should be 'inner', 'left', 'right', 'outer', 'append' or 'union'"
    )


def test_link_index_needs_a_column_name() -> None:
    side = {"feature_group": "GovDataFeature", "index": []}
    _rejects(_recipe(links=[{"join": "inner", "left": side, "right": side}]), "index: List should have at least 1 item")
    side = {"feature_group": "GovDataFeature", "index": [""]}
    _rejects(_recipe(links=[{"join": "inner", "left": side, "right": side}]), "non-empty strings")


@pytest.mark.parametrize(
    "key",
    ["password", "username", "token", "GENESIS_TOKEN", "genesis_credentials", "api_key", "apikey", "client_secret"],
)
def test_a_credential_named_key_is_rejected_wherever_it_appears(key: str) -> None:
    _rejects(_recipe(features=[{"name": "value", "options": {key: "x"}}]), f"{key!r} names a credential")
    _rejects(
        _recipe(features=[{"name": "value", "options": {"DestatisReader": dict(LOCATOR, **{key: "x"})}}]),
        f"options.DestatisReader.{key}: {key!r} names a credential",
    )
    _rejects(_recipe(features=[{"name": "value", "context_options": {key: "x"}}]), f"{key!r} names a credential")
    side = {"feature_group": "GovDataFeature", "index": ["Nr"], "discriminator": {key: "x"}}
    _rejects(_recipe(links=[{"join": "inner", "left": side, "right": side}]), f"{key!r} names a credential")


def test_a_token_shaped_value_is_rejected_wherever_it_appears() -> None:
    message = f"looks like an API token \\({TOKEN_RUN_LENGTH} or more letters and digits"
    _rejects(_recipe(features=[{"name": "value", "options": {"DestatisReader": TOKEN_LIKE}}]), message)
    _rejects(_recipe(features=[TOKEN_LIKE]), message)
    _rejects(_recipe(features=[{"name": "value", "options": {"url": f"https://host/data?key={TOKEN_LIKE}"}}]), message)
    _rejects(_recipe(compliance={"sources": [_source(attribution=TOKEN_LIKE)]}), message)
    _rejects(_recipe(compliance={"sources": [_source(modifications=[TOKEN_LIKE])]}), message)
    _rejects(_recipe(compliance={"sources": [SOURCE], "notes": f"see {TOKEN_LIKE}"}), message)
    side = {
        "feature_group": "GovDataFeature",
        "index": ["Nr"],
        "discriminator": {"BundeswahlleiterinReader": TOKEN_LIKE},
    }
    _rejects(_recipe(links=[{"join": "inner", "left": side, "right": side}]), message)


@pytest.mark.parametrize(
    "value",
    [
        "1" * 40,  # digits only: an id, not a token
        "Donaudampfschifffahrtsgesellschaft",  # letters only
        "einwohner-nach-altersgruppen-und-stadtbezirken",  # slug
        "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv",
        "https://www.umweltbundesamt.de/api/air_data/v4/measures/json?date_from=2025-01-01&station=143&component=3",
        "2026-09-08T12:34:56+00:00",
        "Wahlberechtigte Erststimmen Endgültig",
        "Ab1" * 7,  # one short of the threshold
    ],
)
def test_ordinary_values_pass_the_token_shape(value: str) -> None:
    recipe = Recipe.model_validate(_recipe(features=[{"name": "value", "options": {"reader": value}}]))
    assert recipe.features[0] == {"name": "value", "options": {"reader": value}}


def test_the_sha256_field_is_exempt_but_a_hash_elsewhere_is_not() -> None:
    Recipe.model_validate(_recipe())
    _rejects(_recipe(compliance={"sources": [_source(attribution=SOURCE["sha256"])]}), "looks like an API token")


def test_values_of_the_environments_own_credentials_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENESIS_TOKEN", "sekret-value-1")
    monkeypatch.setenv("REGIONALSTATISTIK_PASSWORD", "p@ss w0rd!")
    uri = "https://genesis.destatis.de/x?token=SEKRET-value-1"
    _rejects(_recipe(compliance={"sources": [_source(dataset_uri=uri)]}), "value of a GENESIS credential")
    encoded = {"name": "value", "options": {"DestatisReader": "https://host/?p=p%40ss%20w0rd%21"}}
    _rejects(_recipe(features=[encoded]), "value of a GENESIS credential")
    _rejects(_recipe(features=[{"name": "value", "options": {"sekret-value-1": "x"}}]), "value of a GENESIS credential")
    Recipe.model_validate(_recipe())


def test_environment_secrets_cover_known_hosts_and_skip_short_values() -> None:
    environ = {"GENESIS_TOKEN": "abc", "REGIONALSTATISTIK_USER": "Max Mustermann", "OTHER_TOKEN": "long-enough-value"}
    secrets = environment_secrets(environ)
    assert "max mustermann" in secrets
    assert "max%20mustermann" in secrets
    assert not any("abc" == secret for secret in secrets)
    assert not any("long-enough" in secret for secret in secrets)


def test_error_messages_never_echo_the_rejected_value(monkeypatch: pytest.MonkeyPatch) -> None:
    error = _rejects(_recipe(features=[{"name": "value", "options": {"DestatisReader": TOKEN_LIKE}}]), "API token")
    assert TOKEN_LIKE not in str(error)
    monkeypatch.setenv("GENESIS_TOKEN", "sekret-value-1")
    error = _rejects(_recipe(compliance={"sources": [SOURCE], "notes": "sekret-value-1"}), "GENESIS credential")
    assert "sekret-value-1" not in str(error)
    error = _rejects(_recipe(features=[{"name": TOKEN_LIKE, "bogus": 1}]), "unknown key")
    assert TOKEN_LIKE not in str(error)
    error = _rejects(_recipe(features=[{"name": "value", "in_features": TOKEN_LIKE}]), "in_features")
    assert TOKEN_LIKE not in str(error)
