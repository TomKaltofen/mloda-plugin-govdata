"""DestatisLocator: table-code shape, host and language validation, coercion, JSON round trip."""

import json

import pytest

from mloda_plugin_govdata.feature_groups.destatis.locator import DestatisLocator


def test_accepts_genesis_online_style_code() -> None:
    assert DestatisLocator("12411-0015").name == "12411-0015"


def test_accepts_regionalstatistik_style_code() -> None:
    assert DestatisLocator("13211-02-05-4").name == "13211-02-05-4"


@pytest.mark.parametrize("bad", ["", "not-a-code", "1241-0015", "12411", "12411-0015-"])
def test_rejects_a_bad_table_code(bad: str) -> None:
    with pytest.raises(ValueError, match="not a recognized GENESIS table code"):
        DestatisLocator(bad)


def test_strips_whitespace_from_the_name() -> None:
    assert DestatisLocator(" 12411-0015 ").name == "12411-0015"


def test_default_host_is_genesis() -> None:
    assert DestatisLocator("12411-0015").host == "genesis"


def test_regionalstatistik_host_is_accepted() -> None:
    assert DestatisLocator("13211-02-05-4", host="regionalstatistik").host == "regionalstatistik"


def test_unknown_host_raises() -> None:
    with pytest.raises(ValueError, match="Unknown GENESIS host"):
        DestatisLocator("12411-0015", host="not-a-host")


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
