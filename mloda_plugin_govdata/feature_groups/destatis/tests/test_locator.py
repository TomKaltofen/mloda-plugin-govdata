"""DestatisLocator: table-code shape, host and language validation, coercion, JSON round trip."""

import json

import pytest

from mloda_plugin_govdata.feature_groups.destatis.core.hosts import GENESIS_ONLINE
from mloda_plugin_govdata.feature_groups.destatis.locator import DestatisLocator


def test_accepts_genesis_online_style_code() -> None:
    assert DestatisLocator("12411-0015").name == "12411-0015"


def test_accepts_regionalstatistik_style_code() -> None:
    assert DestatisLocator("13211-02-05-4").name == "13211-02-05-4"


@pytest.mark.parametrize("bad", ["", "not-a-code", "1241-0015", "12411", "12411-0015-"])
def test_rejects_a_bad_table_code(bad: str) -> None:
    with pytest.raises(ValueError, match="not a recognized GENESIS table code"):
        DestatisLocator(bad)


def test_rejects_a_table_code_over_the_documented_length() -> None:
    # Structurally valid (three dash segments) but over the 15-char spec limit in
    # docs/destatis-options.md; codex and an independent Opus review both flagged this.
    with pytest.raises(ValueError, match="not a recognized GENESIS table code"):
        DestatisLocator("12345-1234-1234-1234")


def test_rejects_a_non_str_name() -> None:
    with pytest.raises(TypeError, match="name must be a str"):
        DestatisLocator(12411)  # type: ignore[arg-type]


def test_strips_whitespace_from_the_name() -> None:
    assert DestatisLocator(" 12411-0015 ").name == "12411-0015"


def test_default_host_is_genesis() -> None:
    assert DestatisLocator("12411-0015").host == "genesis"


def test_regionalstatistik_host_is_accepted() -> None:
    assert DestatisLocator("13211-02-05-4", host="regionalstatistik").host == "regionalstatistik"


def test_unknown_host_raises() -> None:
    with pytest.raises(ValueError, match="Unknown GENESIS host"):
        DestatisLocator("12411-0015", host="not-a-host")


def test_host_accepts_a_genesishost_and_stores_its_name() -> None:
    # resolve_host also accepts a GenesisHost instance; the stored field must stay the
    # canonical name string, not the object, so to_dict/hashing/describe() stay JSON-safe.
    locator = DestatisLocator("12411-0015", host=GENESIS_ONLINE)  # type: ignore[arg-type]
    assert locator.host == "genesis"
    assert locator.to_dict()["host"] == "genesis"


def test_non_german_language_is_rejected() -> None:
    with pytest.raises(ValueError, match="language must be 'de'"):
        DestatisLocator("12411-0015", language="en")


def test_selection_fields_normalize_to_a_tuple() -> None:
    # A list or bare str is not the typed constructor API (that is from_dict, for JSON-native
    # input, which has no tuples); __post_init__ still normalizes it defensively at runtime.
    locator = DestatisLocator(
        "12411-0015",
        regionalkey=["03159", "03152"],  # type: ignore[arg-type]
        classifyingkey1="W",  # type: ignore[arg-type]
    )
    assert locator.regionalkey == ("03159", "03152")
    assert locator.classifyingkey1 == ("W",)


def test_a_non_bool_quality_is_rejected() -> None:
    # tablefile_parameters does "on" if quality else "off": any truthy non-bool (e.g. the string
    # "false" from a config file) would silently send quality=on.
    with pytest.raises(TypeError, match="quality must be a bool"):
        DestatisLocator("12411-0015", quality="false")  # type: ignore[arg-type]


def test_empty_selection_fields_normalize_to_none_not_an_empty_wire_value() -> None:
    # An empty tuple/list or blank string means "no narrowing"; it must match the None default,
    # not become a distinct cache key with an empty parameter value.
    assert DestatisLocator("12411-0015", regionalkey=()) == DestatisLocator("12411-0015")
    assert DestatisLocator("12411-0015", regionalkey=["  "]) == DestatisLocator("12411-0015")  # type: ignore[arg-type]
    assert DestatisLocator("12411-0015", regionalvariable="  ").regionalvariable is None
    assert DestatisLocator("12411-0015", contents=()) == DestatisLocator("12411-0015")


def test_bytes_selection_field_is_rejected() -> None:
    # bytes is a Sequence[int]; iterating it silently yields character codes, not keys.
    with pytest.raises(TypeError, match="not bytes"):
        DestatisLocator("12411-0015", regionalkey=b"03159")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("startyear", "endyear"),
    [(1899, None), (2101, None), (None, 1899), (None, 2101), (2017, 2013)],
)
def test_year_bounds_are_validated(startyear: int | None, endyear: int | None) -> None:
    with pytest.raises(ValueError):
        DestatisLocator("12411-0015", startyear=startyear, endyear=endyear)


def test_year_as_bool_is_rejected() -> None:
    # bool subclasses int; True/False must not silently pass as a year.
    with pytest.raises(TypeError, match="startyear must be an int"):
        DestatisLocator("12411-0015", startyear=True)


def test_locator_is_frozen_and_hashable() -> None:
    a = DestatisLocator("12411-0015")
    b = DestatisLocator("12411-0015")
    assert a == b
    assert hash(a) == hash(b)
    assert {a, b} == {a}
    with pytest.raises(AttributeError):
        a.name = "12411-0010"  # type: ignore[misc]


def test_from_string_is_a_bare_table_code() -> None:
    assert DestatisLocator.from_string("12411-0015") == DestatisLocator("12411-0015")


def test_coerce_passes_through_a_locator_instance() -> None:
    locator = DestatisLocator("12411-0015")
    assert DestatisLocator.coerce(locator) is locator


def test_coerce_accepts_a_string() -> None:
    assert DestatisLocator.coerce("12411-0015") == DestatisLocator("12411-0015")


def test_coerce_accepts_a_plain_dict() -> None:
    assert DestatisLocator.coerce({"name": "12411-0015", "quality": True}) == DestatisLocator(
        "12411-0015", quality=True
    )


def test_coerce_rejects_unusable_values() -> None:
    assert DestatisLocator.coerce(123) is None
    assert DestatisLocator.coerce("") is None
    assert DestatisLocator.coerce(None) is None


def test_from_dict_rejects_an_unknown_field() -> None:
    with pytest.raises(ValueError, match="unknown field"):
        DestatisLocator.from_dict({"name": "12411-0015", "area": "free"})


def test_from_dict_rejects_a_missing_name() -> None:
    with pytest.raises(ValueError, match="missing required field 'name'"):
        DestatisLocator.from_dict({"quality": True})


def test_coerce_of_a_dict_missing_name_raises_the_same_clean_error() -> None:
    with pytest.raises(ValueError, match="missing required field 'name'"):
        DestatisLocator.coerce({"quality": True})


def test_to_dict_round_trips_through_json() -> None:
    locator = DestatisLocator(
        "12411-0015",
        regionalvariable="KREISE",
        regionalkey=("03159", "03152"),
        contents=("BEVSTD",),
        startyear=2013,
        endyear=2017,
        quality=True,
    )
    restored = DestatisLocator.coerce(json.loads(json.dumps(locator.to_dict())))
    assert restored == locator


def test_describe_names_the_table_and_the_non_default_host() -> None:
    assert DestatisLocator("12411-0015").describe() == "12411-0015"
    assert DestatisLocator("13211-02-05-4", host="regionalstatistik").describe() == "13211-02-05-4@regionalstatistik"
