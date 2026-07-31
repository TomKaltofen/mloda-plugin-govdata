"""Bundeswahlleiterin federal election results (M1 elections theme, kerg.csv)."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
from mloda.user import Options

from .core.discovery import ResolvedDistribution
from .core.locator import GovDataLocator
from .core.parse import ColumnType, parse_multi_header_csv
from .reader import BaseGovDataReader

# Feature-option keys steering the multi-header election parse; defaults are the btw25 kerg.csv
# geometry, so a new election file is a per-feature configuration change, not a code change.
OPTION_WAHL_SKIPROWS = "govdata_wahl_skiprows"
OPTION_WAHL_HEADER_ROWS = "govdata_wahl_header_rows"
OPTION_WAHL_LABEL_COLUMNS = "govdata_wahl_label_columns"
OPTION_WAHL_VALUE_TYPE = "govdata_wahl_value_type"


class BundeswahlleiterinReader(BaseGovDataReader):
    """Reads German election-result CSVs with the Bundeswahlleiterin kerg.csv as the default geometry.

    The header geometry defaults to the btw25 kerg.csv layout (5-line preamble, 3-row merged
    header, 4 label columns, integer values) and is overridable per feature via the
    ``OPTION_WAHL_*`` option keys. A degenerate geometry (``header_rows=1``, ``skiprows=0``)
    covers single-header publisher exports, so connecting the next election is a
    configuration step instead of a code change.
    """

    @classmethod
    def _parse(
        cls, path: Path, locator: GovDataLocator, distribution: ResolvedDistribution, options: Options | None = None
    ) -> pa.Table:
        def int_option(key: str, default: int) -> int:
            value = options.get(key) if options is not None else None
            return default if value is None else int(value)  # non-numeric values raise loudly

        raw_value_type = options.get(OPTION_WAHL_VALUE_TYPE) if options is not None else None
        return parse_multi_header_csv(
            path,
            skiprows=int_option(OPTION_WAHL_SKIPROWS, 5),
            header_rows=int_option(OPTION_WAHL_HEADER_ROWS, 3),
            label_columns=int_option(OPTION_WAHL_LABEL_COLUMNS, 4),
            value_type=ColumnType(raw_value_type) if raw_value_type is not None else ColumnType.INTEGER,
        )
