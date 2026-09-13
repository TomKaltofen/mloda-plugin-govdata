"""frames_by_column: distinct columns index cleanly, a shared column never silently reads as absent."""

import pyarrow as pa
import pytest

from mloda_plugin_govdata.recipes import frames_by_column


def test_distinct_columns_index_by_name() -> None:
    left = pa.table({"value": [1, 2]})
    right = pa.table({"Nr": ["01", "02"]})
    frames = frames_by_column([left, right])
    assert frames["value"] is left
    assert frames["Nr"] is right
    assert "value" in frames and frames.get("value") is left
    assert set(frames) == {"value", "Nr"} and len(frames) == 2


def test_a_shared_column_raises_on_every_lookup_form() -> None:
    left = pa.table({"key": [1], "value": [1]})
    right = pa.table({"key": [1], "Nr": ["01"]})
    frames = frames_by_column([left, right])
    assert frames["value"] is left
    assert frames["Nr"] is right
    with pytest.raises(ValueError, match="key"):
        frames["key"]
    with pytest.raises(ValueError, match="key"):
        _ = "key" in frames
    with pytest.raises(ValueError, match="key"):
        frames.get("key")
    # A shared column resolves to no single frame, so it is absent from iteration and length too.
    assert "key" not in iter(frames)
    assert len(frames) == 2
