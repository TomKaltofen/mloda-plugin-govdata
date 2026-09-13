"""Land codes: the constant, the name check against the kerg Land rows and the Destatis DLAND labels."""

from pathlib import Path

import pytest

from mloda_plugin_govdata.feature_groups.destatis.core.parse import parse_ffcsv_zip
from mloda_plugin_govdata.feature_groups.govdata import BundeswahlleiterinReader, GovDataLocator, Provenance
from mloda_plugin_govdata.harmonization.land_codes import (
    LAND_NAMES,
    LandNameError,
    check_land_names,
    land_code,
    land_name,
    normalize_land_name,
)

KERG_URL = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv"
BUNDESGEBIET = "99"
# The full file's federal total row: Nr 99 with an empty "gehört zu"; the sample omits it.
BUNDESGEBIET_ROW = b"99;Bundesgebiet;\n"


def _kerg_land_rows(path: Path) -> list[tuple[str, object]]:
    table = BundeswahlleiterinReader._parse(path, GovDataLocator.from_string(KERG_URL), Provenance("url", KERG_URL))
    columns = (table.column(name).to_pylist() for name in ("Nr", "Gebiet", "gehört zu"))
    return [(nr, name) for nr, name, parent in zip(*columns) if parent == BUNDESGEBIET]


def test_the_sixteen_laender_carry_two_digit_codes_and_distinct_names() -> None:
    assert list(LAND_NAMES) == [f"{n:02d}" for n in range(1, 17)]
    assert len(set(LAND_NAMES.values())) == 16
    for code, name in LAND_NAMES.items():
        assert land_name(code) == name
        assert land_code(name) == code


def test_normalization_ignores_case_spacing_and_umlaut_spelling() -> None:
    assert normalize_land_name("  Baden-Wuerttemberg ") == normalize_land_name("Baden-Württemberg")
    assert normalize_land_name("Straße") == "strasse"
    assert land_code("thueringen") == "16"
    assert land_code("Mecklenburg-Vorpommern") == "13"


def test_the_kerg_land_rows_match_the_constant(govdata_fixtures_dir: Path, tmp_path: Path) -> None:
    sample = (govdata_fixtures_dir / "kerg_sample.csv").read_bytes()
    with_total = tmp_path / "kerg.csv"
    with_total.write_bytes(sample + BUNDESGEBIET_ROW)
    rows = _kerg_land_rows(with_total)
    assert len(rows) == 16  # the Bundesgebiet row has no parent, so the filter leaves it out
    check_land_names(rows)


def test_the_destatis_dland_labels_match_the_constant(ffcsv_fixtures_dir: Path) -> None:
    table = parse_ffcsv_zip((ffcsv_fixtures_dir / "12411-0010_2024_de_flat.zip").read_bytes())
    codes = table.column("1_variable_attribute_code").to_pylist()
    labels = table.column("1_variable_attribute_label").to_pylist()
    check_land_names(zip(codes, labels))


def test_a_swapped_name_is_reported_by_row() -> None:
    rows: list[tuple[str, object]] = list(LAND_NAMES.items())
    rows[0] = ("01", "Hamburg")
    with pytest.raises(LandNameError, match=r"row 0: 01 is 'Schleswig-Holstein', not 'Hamburg'"):
        check_land_names(rows)


def test_a_null_name_cell_is_reported_not_crashed_on() -> None:
    rows: list[tuple[str, object]] = list(LAND_NAMES.items())
    rows[10] = ("11", None)
    with pytest.raises(LandNameError, match=r"row 10: 11 has no name \(NoneType\)"):
        check_land_names(rows)


def test_the_bundesgebiet_row_is_not_a_land() -> None:
    with pytest.raises(LandNameError, match="'99' is not a Land AGS-2 code"):
        land_name(BUNDESGEBIET)
    with pytest.raises(LandNameError, match=r"row 0: '99' is not a Land code"):
        check_land_names([(BUNDESGEBIET, "Bundesgebiet")], complete=False)


def test_completeness_wants_all_sixteen_and_a_repeat_is_always_reported() -> None:
    fifteen: list[tuple[str, object]] = [(code, name) for code, name in LAND_NAMES.items() if code != "16"]
    with pytest.raises(LandNameError, match=r"missing Land codes \['16'\]"):
        check_land_names(fifteen)
    check_land_names(fifteen, complete=False)
    with pytest.raises(LandNameError, match="11 appears 2 times"):
        check_land_names([*fifteen, ("11", "Berlin")], complete=False)
