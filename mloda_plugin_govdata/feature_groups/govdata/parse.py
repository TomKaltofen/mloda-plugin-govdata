"""Deterministic parser for German public-authority CSVs into a typed Arrow table.

Handles the traits that break a naive ``pyarrow.csv`` read: cp1252/latin
encodings, semicolon delimiters, German number formatting (``.`` thousands,
``,`` decimal), German dates, and statistical value markers where ``-`` means
zero (not missing). Parsing into the wrong type fails loudly rather than
silently leaving a column as strings.
"""

from __future__ import annotations

import io
import os
from datetime import date, datetime
from enum import Enum

import pandas as pd
import pyarrow as pa

# Strict-decode first, latin-1 last because it never raises (guaranteed fallback).
ENCODING_LADDER: tuple[str, ...] = ("utf-8-sig", "cp1252", "iso-8859-15", "latin-1")

GERMAN_DATE_FORMAT = "%d.%m.%Y"

# German statistical value markers (Destatis / Genesis convention).
ZERO_MARKERS: frozenset[str] = frozenset({"-"})  # exactly zero, never null
NULL_MARKERS: frozenset[str] = frozenset({".", "...", "/", "x", "()", ""})  # unknown / blocked


class ColumnType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    DATE = "date"


_ARROW_TYPE: dict[ColumnType, pa.DataType] = {
    ColumnType.STRING: pa.string(),
    ColumnType.INTEGER: pa.int64(),
    ColumnType.FLOAT: pa.float64(),
    ColumnType.DATE: pa.date32(),
}


def detect_encoding(data: bytes, ladder: tuple[str, ...] = ENCODING_LADDER) -> str:
    """First encoding in the ladder that decodes the bytes without error."""
    for enc in ladder:
        try:
            data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return ladder[-1]


def _clean_number(raw: str) -> str | None:
    """Apply value markers, then de-Germanize the number, or None for null markers."""
    value = raw.strip()
    if value in ZERO_MARKERS:
        return "0"
    if value in NULL_MARKERS:
        return None
    # German formatting: '.' is the thousands separator, ',' the decimal mark.
    return value.replace(".", "").replace(",", ".")


def _to_int(raw: str) -> int | None:
    cleaned = _clean_number(raw)
    if cleaned is None:
        return None
    number = float(cleaned)
    if not number.is_integer():
        raise ValueError(f"expected an integer, got {raw!r}")
    return int(number)


def _to_float(raw: str) -> float | None:
    cleaned = _clean_number(raw)
    if cleaned is None:
        return None
    return float(cleaned)


def _to_date(raw: str) -> date | None:
    value = raw.strip()
    if value in NULL_MARKERS:
        return None
    return datetime.strptime(value, GERMAN_DATE_FORMAT).date()


def _to_string(raw: str) -> str | None:
    value = raw.strip()
    return None if value == "" else value


def parse_german_csv_bytes(
    data: bytes,
    columns: dict[str, ColumnType] | None = None,
    *,
    sep: str = ";",
    skiprows: int = 0,
    encoding: str | None = None,
) -> pa.Table:
    """Parse German-CSV ``data`` into a typed Arrow table.

    ``columns`` maps column name to type; when omitted every column is read as a
    string. Unknown column names in ``columns`` raise ``KeyError``.
    """
    enc = encoding or detect_encoding(data)
    frame = pd.read_csv(
        io.BytesIO(data),
        sep=sep,
        dtype=str,
        keep_default_na=False,
        na_values=[],
        skiprows=skiprows,
        encoding=enc,
    )
    frame.columns = pd.Index([str(name).strip() for name in frame.columns])
    cells: dict[str, list[str]] = {
        col: ["" if v is None else str(v) for v in frame[col].tolist()] for col in frame.columns
    }
    row_count = len(frame.index)

    # Drop fully-empty trailing rows (a trailing newline can yield one).
    keep = [i for i in range(row_count) if any(cells[col][i].strip() != "" for col in cells)]

    if columns is None:
        columns = {name: ColumnType.STRING for name in cells}

    arrays: dict[str, pa.Array] = {}
    fields: list[pa.Field] = []
    for name, ctype in columns.items():
        if name not in cells:
            raise KeyError(f"column {name!r} not found; available: {list(cells)}")
        raw_values = [cells[name][i] for i in keep]
        if ctype is ColumnType.STRING:
            values: list[object] = [_to_string(v) for v in raw_values]
        elif ctype is ColumnType.INTEGER:
            values = [_to_int(v) for v in raw_values]
        elif ctype is ColumnType.FLOAT:
            values = [_to_float(v) for v in raw_values]
        else:
            values = [_to_date(v) for v in raw_values]
        arrays[name] = pa.array(values, type=_ARROW_TYPE[ctype])
        fields.append(pa.field(name, _ARROW_TYPE[ctype]))

    return pa.table(arrays, schema=pa.schema(fields))


def parse_german_csv(
    path: str | os.PathLike[str],
    columns: dict[str, ColumnType] | None = None,
    *,
    sep: str = ";",
    skiprows: int = 0,
    encoding: str | None = None,
) -> pa.Table:
    """Read ``path`` and parse it with :func:`parse_german_csv_bytes`."""
    with open(path, "rb") as handle:
        data = handle.read()
    return parse_german_csv_bytes(data, columns, sep=sep, skiprows=skiprows, encoding=encoding)
