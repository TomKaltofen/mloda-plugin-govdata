import warnings
from datetime import date
from pathlib import Path

import pytest

from mloda_plugin_govdata.feature_groups.harmonization.core.crosswalk import NutsCrosswalk
from mloda_plugin_govdata.feature_groups.harmonization.core.nuts import (
    UnmatchedKeysError,
    combine_mapping_results,
    map_ags_to_nuts,
)
from mloda_plugin_govdata.feature_groups.harmonization.core.reference.eurostat import (
    LauNutsRow,
    parse_lau_nuts_de_workbook,
)
from mloda_plugin_govdata.feature_groups.harmonization.core.reference.gv_isys import (
    GvIsysChange,
    parse_gv_isys_workbook,
)


def _kreis_change(from_ags: str, to_ags: str) -> GvIsysChange:
    return GvIsysChange(
        change_id="x",
        level="Kreis",
        from_rs=from_ags,
        from_ags=from_ags,
        from_name="x",
        change_type="x",
        to_rs=to_ags,
        to_ags=to_ags,
        to_name="x",
        effective_date_legal=date(2016, 11, 1),
        effective_date_statistical=date(2016, 11, 1),
    )


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
def real_crosswalk(reference_fixtures_dir: Path) -> NutsCrosswalk:
    lau_rows = tuple(parse_lau_nuts_de_workbook(reference_fixtures_dir / "eurostat-lau-nuts-de-extract.xlsx"))
    changes = tuple(parse_gv_isys_workbook(reference_fixtures_dir / "gv-isys-2016-extract.xlsx"))
    return NutsCrosswalk(
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


def test_the_five_adr_0006_hand_mapped_keys(real_crosswalk: NutsCrosswalk) -> None:
    result = map_ags_to_nuts(
        ["11000", "03159", "03159501", "07135", "07140"], crosswalk=real_crosswalk, on_unmatched="raise"
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


def test_slice_0_kreis_merger_old_and_new_codes_agree(real_crosswalk: NutsCrosswalk) -> None:
    # The merged Kreis 03159 is in the crosswalk directly; the retired 03152 and 03156
    # are not (they predate NUTS 2024) and only resolve through the GV-ISys redirect. All
    # three land on the same NUTS-3 code: the pre- and post-merger Gebietsstand of the
    # Kreis code agree within the one NUTS version available here.
    result = map_ags_to_nuts(["03152", "03156", "03159"], crosswalk=real_crosswalk, on_unmatched="raise")
    codes = {m.key: m.nuts3 for m in result.matched}
    assert codes == {"03152": "DE91C", "03156": "DE91C", "03159": "DE91C"}


def test_kreis_redirect_requires_gv_isys_history(real_crosswalk: NutsCrosswalk) -> None:
    bare = NutsCrosswalk(**{**real_crosswalk.__dict__, "gv_isys_changes": ()})
    result = map_ags_to_nuts(["03152"], crosswalk=bare, on_unmatched="flag")
    assert result.matched == ()
    assert result.unmatched[0].key == "03152"


def test_ambiguous_kreis_redirect_is_unmatched_not_picked_arbitrarily() -> None:
    # A split: the same retired Kreis code has two GV-ISys successors with different NUTS-3
    # codes. Picking either silently (e.g. "first match") could assign the wrong region.
    lau_rows = (_row("01002001", "DE111"), _row("01003001", "DE112"))
    changes = (_kreis_change("01001", "01002"), _kreis_change("01001", "01003"))
    crosswalk = NutsCrosswalk(
        gebietsstand="2024",
        nuts_version="2024",
        source="t",
        url="t",
        sha256=None,
        year_range=(2024, 2024),
        lau_rows=lau_rows,
        gv_isys_changes=changes,
    )
    result = map_ags_to_nuts(["01001"], crosswalk=crosswalk, on_unmatched="flag")
    assert result.matched == ()
    assert "ambiguous" in result.unmatched[0].reason


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
    crosswalk = NutsCrosswalk(
        gebietsstand="2024",
        nuts_version="2024",
        source="t",
        url="t",
        sha256=None,
        year_range=(2024, 2024),
        lau_rows=lau_rows,
    )
    result = map_ags_to_nuts(["11000", "02000", "04011", "04012"], crosswalk=crosswalk, on_unmatched="raise")
    codes = {m.key: m.nuts3 for m in result.matched}
    assert codes == {"11000": "DE300", "02000": "DE600", "04011": "DE501", "04012": "DE502"}


# --- Gemeindefreie Gebiete in the unmatched report ---------------------------------------


def test_gemeindefreies_gebiet_not_in_the_crosswalk_is_unmatched(real_crosswalk: NutsCrosswalk) -> None:
    # A Gemeindefreies Gebiet outside the small ADR 0006 extract: general 8-digit
    # Gemeinde/Gemeindefreies-Gebiet resolution beyond exact lookup is D4 stretch scope.
    result = map_ags_to_nuts(["09184901"], crosswalk=real_crosswalk, on_unmatched="flag")
    assert result.matched == ()
    assert "not found" in result.unmatched[0].reason


def test_gemeindefreies_gebiet_present_in_the_table_matches(real_crosswalk: NutsCrosswalk) -> None:
    result = map_ags_to_nuts(["03159501"], crosswalk=real_crosswalk, on_unmatched="raise")
    assert result.matched[0].nuts3 == "DE91C"


# --- Land and ARS: always unmatched, never raised ----------------------------------------


def test_land_and_ars_keys_are_unmatched_not_raised(real_crosswalk: NutsCrosswalk) -> None:
    result = map_ags_to_nuts(["03", "031599501501"], crosswalk=real_crosswalk, on_unmatched="flag")
    assert result.matched == ()
    reasons = {u.key: u.reason for u in result.unmatched}
    assert "out of scope" in reasons["03"]
    assert "out of scope" in reasons["031599501501"]


# --- Kreis spanning two NUTS-3 codes (boundary-reform lag window) ------------------------


def test_kreis_spanning_two_nuts3_codes_raises() -> None:
    lau_rows = (_row("16063001", "DEG0N"), _row("16063002", "DEG0P"))  # same Kreis, two NUTS-3
    crosswalk = NutsCrosswalk(
        gebietsstand="2021",
        nuts_version="2021",
        source="t",
        url="t",
        sha256=None,
        year_range=(2021, 2021),
        lau_rows=lau_rows,
    )
    with pytest.raises(ValueError, match="multiple NUTS-3 codes"):
        map_ags_to_nuts(["16063"], crosswalk=crosswalk, on_unmatched="flag")


# --- NUTS version mismatch raises on combine ----------------------------------------------


def test_combining_across_nuts_versions_raises(real_crosswalk: NutsCrosswalk) -> None:
    other = NutsCrosswalk(**{**real_crosswalk.__dict__, "nuts_version": "2021"})
    result_a = map_ags_to_nuts(["11000"], crosswalk=real_crosswalk, on_unmatched="flag")
    result_b = map_ags_to_nuts(["11000"], crosswalk=other, on_unmatched="flag")
    with pytest.raises(ValueError, match="different NUTS versions"):
        combine_mapping_results([result_a, result_b])


def test_combining_same_version_concatenates(real_crosswalk: NutsCrosswalk) -> None:
    result_a = map_ags_to_nuts(["11000"], crosswalk=real_crosswalk, on_unmatched="flag")
    result_b = map_ags_to_nuts(["07135"], crosswalk=real_crosswalk, on_unmatched="flag")
    combined = combine_mapping_results([result_a, result_b])
    assert {m.key for m in combined.matched} == {"11000", "07135"}


# --- on_unmatched policies ----------------------------------------------------------------


def test_on_unmatched_raise_by_default(real_crosswalk: NutsCrosswalk) -> None:
    with pytest.raises(UnmatchedKeysError):
        map_ags_to_nuts(["99999"], crosswalk=real_crosswalk)


def test_on_unmatched_drop_omits_unmatched(real_crosswalk: NutsCrosswalk) -> None:
    result = map_ags_to_nuts(["11000", "99999"], crosswalk=real_crosswalk, on_unmatched="drop")
    assert result.unmatched == ()
    assert {m.key for m in result.matched} == {"11000"}


def test_on_unmatched_flag_returns_both(real_crosswalk: NutsCrosswalk) -> None:
    result = map_ags_to_nuts(["11000", "99999"], crosswalk=real_crosswalk, on_unmatched="flag")
    assert {m.key for m in result.matched} == {"11000"}
    assert {u.key for u in result.unmatched} == {"99999"}


def test_on_unmatched_rejects_an_invalid_value(real_crosswalk: NutsCrosswalk) -> None:
    # The Literal type hint is not runtime-enforced; a typo must not silently behave like "flag".
    with pytest.raises(ValueError, match="on_unmatched must be"):
        map_ags_to_nuts(["11000"], crosswalk=real_crosswalk, on_unmatched="flga")  # type: ignore[arg-type]


# --- data_year checks -----------------------------------------------------------------------


def test_data_year_omitted_skips_checks(real_crosswalk: NutsCrosswalk) -> None:
    result = map_ags_to_nuts(["11000"], crosswalk=real_crosswalk, on_unmatched="flag")
    assert result.data_year_checked is False


def test_data_year_matching_the_crosswalk_year_is_silent(real_crosswalk: NutsCrosswalk) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = map_ags_to_nuts(["11000"], crosswalk=real_crosswalk, data_year=2024, on_unmatched="flag")
    assert result.data_year_checked is True


def test_data_year_diverging_from_the_crosswalk_year_warns(real_crosswalk: NutsCrosswalk) -> None:
    with pytest.warns(UserWarning, match="diverges"):
        map_ags_to_nuts(["11000"], crosswalk=real_crosswalk, data_year=2020, on_unmatched="flag")


def test_data_year_outside_covered_range_raises(real_crosswalk: NutsCrosswalk) -> None:
    with pytest.raises(ValueError, match="outside the crosswalk's covered range"):
        map_ags_to_nuts(["11000"], crosswalk=real_crosswalk, data_year=1999, on_unmatched="flag")
