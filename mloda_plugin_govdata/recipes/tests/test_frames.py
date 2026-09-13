"""frames_by_column: distinct columns index cleanly, a shared column raises only when looked up."""

import pyarrow as pa
import pytest

from mloda_plugin_govdata.recipes import frames_by_column


def test_distinct_columns_index_by_name() -> None:
    left = pa.table({"value": [1, 2]})
    right = pa.table({"Nr": ["01", "02"]})
    frames = frames_by_column([left, right])
    assert frames["value"] is left
    assert frames["Nr"] is right


def test_a_shared_column_raises_only_when_looked_up() -> None:
    left = pa.table({"key": [1], "value": [1]})
    right = pa.table({"key": [1], "Nr": ["01"]})
    frames = frames_by_column([left, right])
    assert frames["value"] is left
    assert frames["Nr"] is right
    with pytest.raises(ValueError, match="key"):
        frames["key"]
