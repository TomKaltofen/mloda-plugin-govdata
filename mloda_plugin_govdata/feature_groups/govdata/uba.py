"""Umweltbundesamt (UBA) Air Data v4 ``measures`` endpoint: URL builder and JSON flatten.

The environment dataset is publisher-direct REST JSON, not a CSV distribution, so it
has a distinct shape from the GovData / Bundeswahlleiterin CSV readers. The response is
``{request, indices, data}`` where ``data`` is keyed by station then by measurement
start datetime, and each leaf is ``[component id, scope id, value, date end, index]``.
The ``indices.data`` block self-describes that layout, so the flatten reads the column
names from the response rather than hardcoding positions.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode

import pyarrow as pa

from .parse import ColumnType

UBA_AIR_BASE = "https://luftdaten.umweltbundesamt.de/api/air-data/v4"

# Fallback column layout if the response omits a usable ``indices.data`` block.
DEFAULT_MEASURE_LABELS: tuple[str, ...] = (
    "station id",
    "date start",
    "component id",
    "scope id",
    "value",
    "date end",
    "index",
)

# Types for the normalized (underscored) measure columns; unlisted columns read as strings.
# Station/component/scope ids and the air-quality index are integers; value is a float so a
# component reporting fractional concentrations is not truncated; the datetimes stay ISO strings.
MEASURE_COLUMN_TYPES: dict[str, ColumnType] = {
    "station_id": ColumnType.INTEGER,
    "date_start": ColumnType.STRING,
    "component_id": ColumnType.INTEGER,
    "scope_id": ColumnType.INTEGER,
    "value": ColumnType.FLOAT,
    "date_end": ColumnType.STRING,
    "index": ColumnType.INTEGER,
}

_ARROW_TYPE: dict[ColumnType, pa.DataType] = {
    ColumnType.STRING: pa.string(),
    ColumnType.INTEGER: pa.int64(),
    ColumnType.FLOAT: pa.float64(),
}


def uba_measures_url(
    *,
    station: int | str,
    component: int | str,
    scope: int | str,
    date_from: str,
    date_to: str,
    time_from: int = 1,
    time_to: int = 24,
    lang: str = "en",
    base: str = UBA_AIR_BASE,
) -> str:
    """Build a UBA Air Data v4 ``measures`` URL.

    Dates are ``YYYY-MM-DD``; ``time_from``/``time_to`` are hour slots 1-24. Parameter
    order is fixed so the same query always yields the same URL (a stable cache key).
    """
    params = {
        "date_from": date_from,
        "time_from": time_from,
        "date_to": date_to,
        "time_to": time_to,
        "station": station,
        "component": component,
        "scope": scope,
        "lang": lang,
    }
    return f"{base}/measures/json?{urlencode(params)}"


def _normalize(label: str) -> str:
    """A response label like ``"date start"`` becomes the column name ``"date_start"``."""
    return label.strip().replace(" ", "_")


def _measure_column_names(payload: dict[str, Any]) -> list[str]:
    """Read the column layout from ``indices.data``, falling back to the known layout.

    ``indices.data`` is ``{<station label>: {<datetime label>: [<value labels...>]}}``; the
    flattened row is ``[station, datetime, *values]``, so the names follow that order.
    """
    raw: tuple[str, ...] | list[str] = DEFAULT_MEASURE_LABELS
    indices = payload.get("indices")
    if isinstance(indices, dict):
        outer = indices.get("data")
        if isinstance(outer, dict) and outer:
            station_label = next(iter(outer))
            inner = outer[station_label]
            if isinstance(inner, dict) and inner:
                datetime_label = next(iter(inner))
                value_labels = inner[datetime_label]
                if isinstance(value_labels, list) and all(isinstance(v, str) for v in value_labels):
                    raw = [station_label, datetime_label, *value_labels]
    names = [_normalize(str(label)) for label in raw]
    if len(set(names)) != len(names):
        raise ValueError(f"UBA measures column names are not unique: {names}")
    return names


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _to_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _typed_table(columns: dict[str, list[Any]], names: list[str]) -> pa.Table:
    arrays: dict[str, pa.Array] = {}
    fields: list[pa.Field] = []
    for name in names:
        ctype = MEASURE_COLUMN_TYPES.get(name, ColumnType.STRING)
        raw = columns[name]
        if ctype is ColumnType.INTEGER:
            values: list[object] = [_to_int(v) for v in raw]
        elif ctype is ColumnType.FLOAT:
            values = [_to_float(v) for v in raw]
        else:
            values = [_to_string(v) for v in raw]
        arrays[name] = pa.array(values, type=_ARROW_TYPE[ctype])
        fields.append(pa.field(name, _ARROW_TYPE[ctype]))
    return pa.table(arrays, schema=pa.schema(fields))


def parse_uba_measures_bytes(data: bytes) -> pa.Table:
    """Flatten a UBA ``measures`` JSON response into a typed Arrow table (one row per reading).

    One row per (station, measurement start) pair. Missing leaf cells and ``null`` values
    become nulls. Raises ``ValueError`` if the payload has no ``data`` object.
    """
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("UBA measures payload is not a JSON object")
    series_by_station = payload.get("data")
    if not isinstance(series_by_station, dict):
        raise ValueError("UBA measures payload has no 'data' object")

    names = _measure_column_names(payload)
    station_col, datetime_col, value_cols = names[0], names[1], names[2:]
    columns: dict[str, list[Any]] = {name: [] for name in names}

    for station_id, series in series_by_station.items():
        if not isinstance(series, dict):
            continue
        for date_start, leaf in series.items():
            cells = list(leaf) if isinstance(leaf, list) else []
            columns[station_col].append(station_id)
            columns[datetime_col].append(date_start)
            for i, col in enumerate(value_cols):
                columns[col].append(cells[i] if i < len(cells) else None)

    return _typed_table(columns, names)


def parse_uba_measures(path: str | os.PathLike[str]) -> pa.Table:
    """Read ``path`` and flatten it with :func:`parse_uba_measures_bytes`."""
    with open(path, "rb") as handle:
        data = handle.read()
    return parse_uba_measures_bytes(data)
