"""Level 1: deterministic German-CSV parsing on captured byte fixtures."""

import datetime
from pathlib import Path

import pyarrow as pa
import pytest

from mloda_plugin_govdata.feature_groups.govdata.parse import (
    ColumnType,
    detect_encoding,
    parse_german_csv,
    parse_german_csv_bytes,
)

POPULATION_COLUMNS: dict[str, ColumnType] = {
    "Stichtag": ColumnType.DATE,
    "Stadtbezirk": ColumnType.STRING,
    "Alter in 10 Gruppen": ColumnType.STRING,
    "Einwohner": ColumnType.INTEGER,
}

VALUE_MARKER_COLUMNS: dict[str, ColumnType] = {
    "Stichtag": ColumnType.DATE,
    "Gebiet": ColumnType.STRING,
    "Wert": ColumnType.INTEGER,
}


def test_detect_encoding_population(fixtures_dir: Path) -> None:
    data = (fixtures_dir / "population_sample.csv").read_bytes()
    assert detect_encoding(data) == "cp1252"
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")


def test_detect_encoding_prefers_utf8_sig_with_bom() -> None:
    assert detect_encoding("Wert\r\n123\r\n".encode("utf-8-sig")) == "utf-8-sig"


def test_detect_encoding_falls_back_for_cp1252_undefined_byte() -> None:
    # 0x81 is undefined in cp1252, so the ladder must reach an 8859 fallback.
    assert detect_encoding(b"\x81") in {"iso-8859-15", "latin-1"}


def test_parse_population_sample(fixtures_dir: Path) -> None:
    table = parse_german_csv(fixtures_dir / "population_sample.csv", POPULATION_COLUMNS)
    assert table.schema.names == ["Stichtag", "Stadtbezirk", "Alter in 10 Gruppen", "Einwohner"]
    assert table.num_rows == 1000
    assert table.schema.field("Stichtag").type == pa.date32()
    assert table.schema.field("Einwohner").type == pa.int64()
    first = table.slice(0, 1).to_pylist()[0]
    assert first["Stichtag"] == datetime.date(1986, 6, 30)
    assert first["Stadtbezirk"] == "Mitte"
    assert first["Einwohner"] == 494


def test_value_markers_map_correctly(fixtures_dir: Path) -> None:
    table = parse_german_csv(fixtures_dir / "value_markers.csv", VALUE_MARKER_COLUMNS)
    # '-' -> 0 (never null); '.', '...', '/', 'x' -> null; '1.234' -> 1234.
    assert table.column("Wert").to_pylist() == [0, 123, None, None, None, None, 1234]
    # cp1252 umlauts decode correctly.
    assert "Möhringen" in table.column("Gebiet").to_pylist()


def test_unknown_columns_default_to_string(fixtures_dir: Path) -> None:
    table = parse_german_csv(fixtures_dir / "value_markers.csv")
    assert all(field_type == pa.string() for field_type in table.schema.types)
    # Untyped: the '-' marker is preserved verbatim as a string.
    assert table.column("Wert").to_pylist()[0] == "-"


def test_missing_column_raises(fixtures_dir: Path) -> None:
    with pytest.raises(KeyError):
        parse_german_csv(fixtures_dir / "value_markers.csv", {"DoesNotExist": ColumnType.STRING})


def test_integer_validation_raises_on_non_numeric() -> None:
    data = "Wert\r\nnotanumber\r\n".encode("cp1252")
    with pytest.raises(ValueError):
        parse_german_csv_bytes(data, {"Wert": ColumnType.INTEGER})


def test_date_validation_raises_on_bad_date() -> None:
    data = "Stichtag\r\n99.99.9999\r\n".encode("cp1252")
    with pytest.raises(ValueError):
        parse_german_csv_bytes(data, {"Stichtag": ColumnType.DATE})


def test_large_integer_parses_exactly() -> None:
    # Values above 2**53 must not be rounded through float.
    big = 9007199254740993
    data = f"Wert\r\n{big}\r\n".encode("cp1252")
    table = parse_german_csv_bytes(data, {"Wert": ColumnType.INTEGER})
    assert table.column("Wert").to_pylist() == [big]
