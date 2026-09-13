import pytest
from hypothesis import given
from hypothesis import strategies as st

from mloda_plugin_govdata.harmonization.keys import (
    ARS_LENGTH,
    AgsLevel,
    detect_level,
    normalize_key,
    normalize_keys,
    repair_bbsr_kreis_key,
)

_VALID_LENGTHS = (AgsLevel.LAND, AgsLevel.KREIS, AgsLevel.GEMEINDE, ARS_LENGTH)


@given(st.sampled_from(_VALID_LENGTHS), st.integers(min_value=0))
def test_detect_level_preserves_valid_string_keys(level: int, seed: int) -> None:
    # A valid, already zero-padded key round-trips: level detection never mutates it.
    digits = str(seed % (10**level)).zfill(level)
    assert detect_level(digits) == level
    assert normalize_key(digits, level=level) == digits  # idempotent for an already-valid key


@pytest.mark.parametrize("key", ["", "abc", "1a", "123", "123456", "1234567890123"])
def test_detect_level_rejects_invalid_keys(key: str) -> None:
    with pytest.raises(ValueError, match="not a numeric|not a valid"):
        detect_level(key)


def test_normalize_key_pads_short_values() -> None:
    assert normalize_key(159, level=AgsLevel.KREIS) == "00159"
    assert normalize_key("159", level=AgsLevel.KREIS) == "00159"


def test_normalize_key_rejects_overflow() -> None:
    with pytest.raises(ValueError, match="more than"):
        normalize_key(123456, level=AgsLevel.KREIS)


def test_repair_bbsr_kreis_key_strips_gemeinde_suffix() -> None:
    assert repair_bbsr_kreis_key(3152000) == "03152"
    assert repair_bbsr_kreis_key("3152000") == "03152"


def test_repair_bbsr_kreis_key_raises_without_000_suffix() -> None:
    with pytest.raises(ValueError, match="000.*Gemeinde suffix"):
        repair_bbsr_kreis_key(3152001)


def test_normalize_keys_mixed_levels_raise() -> None:
    with pytest.raises(ValueError, match="mixed AGS/ARS levels"):
        normalize_keys(["11000", "03159"] + ["03159016"])  # Kreis + Kreis + Gemeinde


def test_normalize_keys_returns_shared_level() -> None:
    keys, level = normalize_keys(["11000", "03159"])
    assert keys == ["11000", "03159"]
    assert level == AgsLevel.KREIS


def test_normalize_keys_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="no keys given"):
        normalize_keys([])
