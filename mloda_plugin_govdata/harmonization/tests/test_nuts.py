import warnings
from pathlib import Path

import pytest

from mloda_plugin_govdata.harmonization.edition import Edition
from mloda_plugin_govdata.harmonization.nuts import (
    UnmatchedKeysError,
    combine_mapping_results,
    map_ags_to_nuts,
)
from mloda_plugin_govdata.harmonization.reference.eurostat import LauNutsRow, parse_lau_nuts_de_workbook
from mloda_plugin_govdata.harmonization.reference.gv_isys import parse_gv_isys_workbook


def _row(lau_code: str, nuts3: str) -> LauNutsRow:
    return LauNutsRow(
        period=2024,
        nuts3=nuts3,
        lau_code=lau_code,
        lau_name=lau_code,
        change="N",
        population=0,
        total_area_m2=0,
        degurba=1,
        coastal_area=False,
    )


@pytest.fixture
def real_edition(reference_fixtures_dir: Path) -> Edition:
    lau_rows = tuple(parse_lau_nuts_de_workbook(reference_fixtures_dir / "eurostat-lau-nuts-de-extract.xlsx"))
    changes = tuple(parse_gv_isys_workbook(reference_fixtures_dir / "gv-isys-2016-extract.xlsx"))
    return Edition(
        gebietsstand="2024",
        nuts_version="2024",
        source="test",
        url="test://",
        sha256=None,
        year_range=(2016, 2024),
        lau_rows=lau_rows,
        gv_isys_changes=changes,
    )


# --- the five hand-mapped keys from ADR 0006 --------------------------------------------


def test_the_five_adr_0006_hand_mapped_keys(real_edition: Edition) -> None:
    result = map_ags_to_nuts(
        ["11000", "03159", "03159501", "07135", "07140"], edition=real_edition, on_unmatched="raise"
    )
    by_key = {m.key: m.nuts3 for m in result.matched}
    assert by_key == {
        "11000": "DE300",
        "03159": "DE91C",
        "03159501": "DE91C",
        "07135": "DEB1C",
        "07140": "DEB1D",
    }


# --- slice-0 Kreis merger: old and new Kreis codes agree --------------------------------


def test_slice_0_kreis_merger_old_and_new_codes_agree(real_edition: Edition) -> None:
    # The merged Kreis 03159 is in this edition's crosswalk directly; the retired 03152
    # and 03156 are not (they predate NUTS 2024) and only resolve through the GV-ISys
    # redirect. All three land on the same NUTS-3 code in the current edition: "both
    # editions" (checklist) means both the pre- and post-merger Gebietsstand of the
    # Kreis code, not two different NUTS editions (only one is available here).
    result = map_ags_to_nuts(["03152", "03156", "03159"], edition=real_edition, on_unmatched="raise")
    codes = {m.key: m.nuts3 for m in result.matched}
    assert codes == {"03152": "DE91C", "03156": "DE91C", "03159": "DE91C"}


def test_kreis_redirect_requires_gv_isys_history(real_edition: Edition) -> None:
    bare_edition = Edition(**{**real_edition.__dict__, "gv_isys_changes": ()})
    result = map_ags_to_nuts(["03152"], edition=bare_edition, on_unmatched="flag")
    assert result.matched == ()
    assert result.unmatched[0].key == "03152"


# --- city-states -------------------------------------------------------------------------


def test_city_states_are_consistent() -> None:
    # Berlin, Hamburg and Bremen are simultaneously Land, Kreis, and (for Berlin/Hamburg)
    # a single Gemeinde; Bremerhaven is a second, separate Kreis inside the Land Bremen.
    lau_rows = (
        _row("11000000", "DE300"),  # Berlin
        _row("02000000", "DE600"),  # Hamburg
        _row("04011000", "DE501"),  # Bremen, Stadt
        _row("04012000", "DE502"),  # Bremerhaven
    )
    edition = Edition(
        gebietsstand="2024",
        nuts_version="2024",
        source="t",
        url="t",
        sha256=None,
        year_range=(2024, 2024),
        lau_rows=lau_rows,
    )
    result = map_ags_to_nuts(["11000", "02000", "04011", "04012"], edition=edition, on_unmatched="raise")
    codes = {m.key: m.nuts3 for m in result.matched}
    assert codes == {"11000": "DE300", "02000": "DE600", "04011": "DE501", "04012": "DE502"}


# --- Gemeindefreie Gebiete in the unmatched report ---------------------------------------


def test_gemeindefreies_gebiet_not_in_this_editions_table_is_unmatched(real_edition: Edition) -> None:
    # A Gemeindefreies Gebiet outside the small ADR 0006 extract: general 8-digit
    # Gemeinde/Gemeindefreies-Gebiet resolution beyond exact lookup is D4 stretch scope.
    result = map_ags_to_nuts(["09184901"], edition=real_edition, on_unmatched="flag")
    assert result.matched == ()
    assert "not found" in result.unmatched[0].reason


def test_gemeindefreies_gebiet_present_in_the_table_matches(real_edition: Edition) -> None:
    result = map_ags_to_nuts(["03159501"], edition=real_edition, on_unmatched="raise")
    assert result.matched[0].nuts3 == "DE91C"


# --- Land and ARS: always unmatched, never raised ----------------------------------------


def test_land_and_ars_keys_are_unmatched_not_raised(real_edition: Edition) -> None:
    result = map_ags_to_nuts(["03", "031599501501"], edition=real_edition, on_unmatched="flag")
    assert result.matched == ()
    reasons = {u.key: u.reason for u in result.unmatched}
    assert "out of scope" in reasons["03"]
    assert "D4 stretch" in reasons["031599501501"]


# --- Kreis spanning two NUTS-3 codes (edition-boundary lag window) -----------------------


def test_kreis_spanning_two_nuts3_codes_raises() -> None:
    lau_rows = (_row("16063001", "DEG0N"), _row("16063002", "DEG0P"))  # same Kreis, two NUTS-3
    edition = Edition(
        gebietsstand="2021",
        nuts_version="2021",
        source="t",
        url="t",
        sha256=None,
        year_range=(2021, 2021),
        lau_rows=lau_rows,
    )
    with pytest.raises(ValueError, match="multiple NUTS-3 codes"):
        map_ags_to_nuts(["16063"], edition=edition, on_unmatched="flag")


# --- edition (NUTS version) mismatch raises on combine ------------------------------------


def test_combining_across_nuts_versions_raises(real_edition: Edition) -> None:
    other_edition = Edition(**{**real_edition.__dict__, "nuts_version": "2021"})
    result_a = map_ags_to_nuts(["11000"], edition=real_edition, on_unmatched="flag")
    result_b = map_ags_to_nuts(["11000"], edition=other_edition, on_unmatched="flag")
    with pytest.raises(ValueError, match="different NUTS versions"):
        combine_mapping_results([result_a, result_b])


def test_combining_same_version_concatenates(real_edition: Edition) -> None:
    result_a = map_ags_to_nuts(["11000"], edition=real_edition, on_unmatched="flag")
    result_b = map_ags_to_nuts(["07135"], edition=real_edition, on_unmatched="flag")
    combined = combine_mapping_results([result_a, result_b])
    assert {m.key for m in combined.matched} == {"11000", "07135"}


# --- on_unmatched policies ----------------------------------------------------------------


def test_on_unmatched_raise_by_default(real_edition: Edition) -> None:
    with pytest.raises(UnmatchedKeysError):
        map_ags_to_nuts(["99999"], edition=real_edition)


def test_on_unmatched_drop_omits_unmatched(real_edition: Edition) -> None:
    result = map_ags_to_nuts(["11000", "99999"], edition=real_edition, on_unmatched="drop")
    assert result.unmatched == ()
    assert {m.key for m in result.matched} == {"11000"}


def test_on_unmatched_flag_returns_both(real_edition: Edition) -> None:
    result = map_ags_to_nuts(["11000", "99999"], edition=real_edition, on_unmatched="flag")
    assert {m.key for m in result.matched} == {"11000"}
    assert {u.key for u in result.unmatched} == {"99999"}


# --- data_year checks -----------------------------------------------------------------------


def test_data_year_omitted_skips_checks(real_edition: Edition) -> None:
    result = map_ags_to_nuts(["11000"], edition=real_edition, on_unmatched="flag")
    assert result.data_year_checked is False


def test_data_year_matching_edition_year_is_silent(real_edition: Edition) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = map_ags_to_nuts(["11000"], edition=real_edition, data_year=2024, on_unmatched="flag")
    assert result.data_year_checked is True


def test_data_year_diverging_from_edition_year_warns(real_edition: Edition) -> None:
    with pytest.warns(UserWarning, match="diverges"):
        map_ags_to_nuts(["11000"], edition=real_edition, data_year=2020, on_unmatched="flag")


def test_data_year_outside_covered_range_raises(real_edition: Edition) -> None:
    with pytest.raises(ValueError, match="outside this edition's covered range"):
        map_ags_to_nuts(["11000"], edition=real_edition, data_year=1999, on_unmatched="flag")
