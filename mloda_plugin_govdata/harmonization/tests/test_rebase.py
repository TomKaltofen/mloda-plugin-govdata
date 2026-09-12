import csv
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from mloda_plugin_govdata.feature_groups.destatis.core.parse import parse_ffcsv_zip
from mloda_plugin_govdata.harmonization.rebase import (
    DEFAULT_TOLERANCE,
    Flag,
    IssueKind,
    KeyEdition,
    Observation,
    RebasedRow,
    RebaseError,
    ShareKind,
    ShareSumError,
    ValidityError,
    observations_from_columns,
    rebase,
)
from mloda_plugin_govdata.harmonization.reference.bbsr import UmsteigeschluesselRow, parse_bbsr_kreise_workbook
from mloda_plugin_govdata.harmonization.reference.sources import BBSR_KREISE

GOETTINGEN_ZIP = "12411-0015_2013-2017_de_flat.zip"
COCHEM_ZELL_ZIP = "12411-0015_2013-2014_de_flat.zip"


def _row(
    source: str, target: str, share: float, *, from_year: int = 2015, to_year: int = 2016
) -> UmsteigeschluesselRow:
    return UmsteigeschluesselRow(from_year, to_year, source, source, share, share, share, 0.0, 0.0, 0.0, target, target)


def _ffcsv_observations(path: Path) -> list[Observation]:
    table = parse_ffcsv_zip(path.read_bytes())
    return observations_from_columns(
        table.column("1_variable_attribute_code").to_pylist(),
        table.column("time").to_pylist(),
        table.column("value").to_pylist(),
        table.column("value_marker").to_pylist(),
    )


def _expected(path: Path) -> list[tuple[str, int, int, Flag, tuple[str, ...]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [
            (
                r["key"],
                int(r["year"]),
                int(r["value"]),
                Flag(r["flag"]),
                tuple(r["sources"].split("+")) if r["sources"] else (),
            )
            for r in csv.DictReader(handle)
        ]


def _cells(rows: tuple[RebasedRow, ...]) -> list[tuple[str, int, int, Flag, tuple[str, ...]]]:
    return [(r.key, r.year, round(r.value or 0), r.flag, r.sources) for r in rows]


@pytest.fixture
def bbsr_keys(reference_fixtures_dir: Path) -> list[UmsteigeschluesselRow]:
    return parse_bbsr_kreise_workbook(reference_fixtures_dir / "bbsr-ref-kreise-extract.xlsx")


@pytest.fixture
def goettingen(ffcsv_fixtures_dir: Path) -> list[Observation]:
    return _ffcsv_observations(ffcsv_fixtures_dir / GOETTINGEN_ZIP)


# --- C2: the named multi-year Kreis series across the slice-0 Gebietsstand change ------------


def test_c2_goettingen_series_rebased_onto_gebietsstand_2016_cell_for_cell(
    fixtures_dir: Path, goettingen: list[Observation], bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    result = rebase(goettingen, keys=bbsr_keys, from_year=2015, to_year=2016, share="population")

    assert _cells(result.rows) == _expected(fixtures_dir / "c2-goettingen-2016.csv")
    # Merger shares are exactly 1, so the re-based sums are exact, not merely rounded.
    assert [r.value for r in result.rows] == [322616.0, 324013.0, 329538.0, 327065.0, 328036.0]
    assert result.edition == KeyEdition(
        BBSR_KREISE.name, BBSR_KREISE.url, BBSR_KREISE.sha256, 2015, 2016, ShareKind.POPULATION
    )
    assert result.edition.sheet == "2015-2016"
    assert result.census_breaks == ()


def test_dash_cells_outside_validity_are_excluded_and_reported_never_summed(
    goettingen: list[Observation], bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    result = rebase(goettingen, keys=bbsr_keys, from_year=2015, to_year=2016)
    excluded = {(i.key, i.year) for i in result.issues_of(IssueKind.NOT_APPLICABLE)}
    assert excluded == {
        ("03159", 2013),
        ("03159", 2014),
        ("03159", 2015),
        ("03152", 2016),
        ("03152", 2017),
        ("03156", 2016),
        ("03156", 2017),
    }
    assert {r.key for r in result.rows} == {"03159"}
    rebased = [r for r in result.rows if r.flag is Flag.REBASED]
    assert all(r.sources == ("03152", "03156") for r in rebased)  # 03159's own "-" cells never enter the sum


def test_known_stale_share_defect_is_tolerated_for_unrequested_keys_and_named(
    goettingen: list[Observation], bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    result = rebase(goettingen, keys=bbsr_keys, from_year=2015, to_year=2016)
    reported = {i.key: i.detail for i in result.issues_of(IssueKind.SHARE_SUM)}
    assert set(reported) == {"07135", "07137"}
    assert "0.9828486" in reported["07135"]
    assert "0.0171514" in reported["07137"]
    assert result.issues_of(IssueKind.DUPLICATE_PAIR) == ()
    assert result.issues_of(IssueKind.ZERO_SHARE) == ()


def test_known_stale_share_defect_raises_when_the_defective_key_is_requested(
    bbsr_keys: list[UmsteigeschluesselRow],
) -> None:
    with pytest.raises(ShareSumError, match=r"07135: population shares sum to 0\.9828486 on sheet 2015-2016"):
        rebase([Observation("07135", 2015, 62400.0)], keys=bbsr_keys, from_year=2015, to_year=2016)


def test_missing_intermediate_sheets_are_reported_as_unverified(
    goettingen: list[Observation], bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    # The extract has no 2014-2015 and no 2016-2017 sheet, so those years cannot be confirmed unchanged.
    result = rebase(goettingen, keys=bbsr_keys, from_year=2015, to_year=2016)
    unverified = {(i.key, i.year) for i in result.issues_of(IssueKind.UNVERIFIED_YEAR)}
    assert unverified == {("03152", 2014), ("03156", 2014), ("03159", 2017)}

    identity = [
        _row("03152", "03152", 1.0, from_year=2014, to_year=2015),
        _row("03156", "03156", 1.0, from_year=2014, to_year=2015),
        _row("03159", "03159", 1.0, from_year=2016, to_year=2017),
    ]
    complete = rebase(goettingen, keys=[*bbsr_keys, *identity], from_year=2015, to_year=2016)
    assert complete.issues_of(IssueKind.UNVERIFIED_YEAR) == ()
    assert complete.rows == result.rows


# --- the fractional case ----------------------------------------------------------------------


def test_fractional_case_matches_the_expected_values_to_the_integer(
    fixtures_dir: Path, ffcsv_fixtures_dir: Path, bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    observations = _ffcsv_observations(ffcsv_fixtures_dir / COCHEM_ZELL_ZIP)
    inputs = list(observations)
    result = rebase(observations, keys=bbsr_keys, from_year=2013, to_year=2014)

    assert _cells(result.rows) == _expected(fixtures_dir / "c2-cochem-zell-2014.csv")
    values = {(r.key, r.year): r.value for r in result.rows}
    stays = values[("07135", 2013)]
    moved = (values[("07140", 2013)] or 0) - 100770
    assert stays == pytest.approx(62118, abs=1e-6)
    assert moved == pytest.approx(1084, abs=1e-6)
    assert (stays or 0) + moved == pytest.approx(63202, abs=1e-6)  # totals conserved; nothing rounded
    assert observations == inputs  # inputs are never mutated; the observed 100,770 lives only in the input
    assert result.issues == ()


# --- share-sum check, duplicates, zero shares -------------------------------------------------


def test_share_sum_beyond_tolerance_raises_for_requested_keys_only() -> None:
    keys = [
        _row("01001", "01001", 0.6),
        _row("01001", "01002", 0.3),
        _row("01002", "01002", 1.0),
        _row("01003", "01003", 0.5),
    ]
    with pytest.raises(ShareSumError, match="01001: population shares sum to 0.9000000"):
        rebase([Observation("01001", 2015, 100.0)], keys=keys, from_year=2015, to_year=2016)
    result = rebase([Observation("01002", 2015, 100.0)], keys=keys, from_year=2015, to_year=2016)
    assert {i.key for i in result.issues_of(IssueKind.SHARE_SUM)} == {"01001", "01003"}


def test_share_sum_inside_tolerance_is_renormalized_so_totals_are_conserved() -> None:
    keys = [_row("01001", "01001", 0.5), _row("01001", "01002", 0.5000004)]
    observations = [Observation("01001", 2015, 1000.0)]
    result = rebase(observations, keys=keys, from_year=2015, to_year=2016, tolerance=1e-6)
    values = {r.key: r.value or 0 for r in result.rows}
    assert values["01001"] + values["01002"] == pytest.approx(1000.0, abs=1e-9)
    assert values["01001"] == pytest.approx(1000 * 0.5 / 1.0000004)
    with pytest.raises(ShareSumError):
        rebase(observations, keys=keys, from_year=2015, to_year=2016, tolerance=1e-7)


def test_duplicate_pair_raises_for_requested_keys_and_is_reported_otherwise() -> None:
    keys = [_row("01001", "01002", 0.5), _row("01001", "01002", 0.5), _row("01002", "01002", 1.0)]
    with pytest.raises(RebaseError, match="01001 -> 01002 appears 2 times"):
        rebase([Observation("01001", 2015, 1.0)], keys=keys, from_year=2015, to_year=2016)
    result = rebase([Observation("01002", 2015, 1.0)], keys=keys, from_year=2015, to_year=2016)
    assert [i.key for i in result.issues_of(IssueKind.DUPLICATE_PAIR)] == ["01001"]


def test_zero_share_rows_are_reported_and_contribute_nothing() -> None:
    keys = [_row("01001", "01001", 1.0), _row("01001", "01002", 0.0), _row("01002", "01002", 1.0)]
    observations = [Observation("01001", 2015, 10.0), Observation("01002", 2015, 20.0)]
    result = rebase(observations, keys=keys, from_year=2015, to_year=2016)
    assert [(i.key, "01001 -> 01002" in i.detail) for i in result.issues_of(IssueKind.ZERO_SHARE)] == [("01001", True)]
    rows = {r.key: r for r in result.rows}
    assert (rows["01002"].value, rows["01002"].flag, rows["01002"].sources) == (20.0, Flag.OBSERVED, ())


def test_negative_share_raises_for_requested_keys_and_is_reported_otherwise() -> None:
    keys = [_row("01001", "01001", 1.2), _row("01001", "01002", -0.2), _row("01002", "01002", 1.0)]
    with pytest.raises(RebaseError, match="negative population share"):
        rebase([Observation("01001", 2015, 1.0)], keys=keys, from_year=2015, to_year=2016)
    result = rebase([Observation("01002", 2015, 1.0)], keys=keys, from_year=2015, to_year=2016)
    assert [i.key for i in result.issues_of(IssueKind.NEGATIVE_SHARE)] == ["01001"]


@given(
    weights=st.lists(st.floats(min_value=0.01, max_value=1.0), min_size=1, max_size=5),
    value=st.floats(min_value=0.0, max_value=1e8),
)
def test_rebasing_conserves_the_total_and_scales_each_target_by_its_share(weights: list[float], value: float) -> None:
    total = sum(weights)
    shares = [w / total for w in weights]
    targets = [f"0100{i}" for i in range(len(shares))]
    keys = [_row("01001", target, share) for target, share in zip(targets, shares)]
    result = rebase([Observation("01001", 2015, value)], keys=keys, from_year=2015, to_year=2016)
    values = {r.key: r.value or 0 for r in result.rows}
    assert sum(values.values()) == pytest.approx(value, rel=1e-9, abs=1e-6)
    for target, share in zip(targets, shares):
        assert values[target] == pytest.approx(value * share, rel=1e-9, abs=1e-6)


@given(delta=st.floats(min_value=-0.4, max_value=0.4).filter(lambda d: abs(d) > 1e-9))
def test_share_sums_off_by_more_than_the_tolerance_raise_and_inside_it_renormalize(delta: float) -> None:
    assume(abs(abs(delta) - DEFAULT_TOLERANCE) > 1e-9)  # float error at the exact boundary is not the property
    keys = [_row("01001", "01001", 0.5), _row("01001", "01002", 0.5 + delta)]
    observations = [Observation("01001", 2015, 1000.0)]
    if abs(delta) > DEFAULT_TOLERANCE:
        with pytest.raises(ShareSumError):
            rebase(observations, keys=keys, from_year=2015, to_year=2016)
    else:
        strict = rebase(observations, keys=keys, from_year=2015, to_year=2016)
        assert sum(r.value or 0 for r in strict.rows) == pytest.approx(1000.0)
    loose = rebase(observations, keys=keys, from_year=2015, to_year=2016, tolerance=0.45)
    assert sum(r.value or 0 for r in loose.rows) == pytest.approx(1000.0)


# --- validity, unmatched keys, null inputs ----------------------------------------------------


def test_numeric_value_outside_validity_raises(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    with pytest.raises(ValidityError, match="03159 carries a value for 2015 .* does not exist before 31.12.2016"):
        rebase([Observation("03159", 2015, 1.0)], keys=bbsr_keys, from_year=2015, to_year=2016)
    with pytest.raises(ValidityError, match="03152 carries a value for 2016 .* does not exist from 31.12.2016 on"):
        rebase([Observation("03152", 2016, 1.0)], keys=bbsr_keys, from_year=2015, to_year=2016)


def test_unmatched_keys_follow_the_on_unmatched_policy(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    observations = [Observation("03152", 2015, 5.0), Observation("09999", 2015, 1.0)]
    with pytest.raises(RebaseError, match="not on key sheet 2015-2016: 09999"):
        rebase(observations, keys=bbsr_keys, from_year=2015, to_year=2016)
    flagged = rebase(observations, keys=bbsr_keys, from_year=2015, to_year=2016, on_unmatched="flag")
    assert [(i.key, i.year) for i in flagged.issues_of(IssueKind.UNMATCHED)] == [("09999", 2015)]
    dropped = rebase(observations, keys=bbsr_keys, from_year=2015, to_year=2016, on_unmatched="drop")
    assert dropped.issues_of(IssueKind.UNMATCHED) == ()
    assert [(r.key, r.value, r.sources) for r in dropped.rows] == [("03159", 5.0, ("03152",))]
    with pytest.raises(ValueError, match="on_unmatched must be"):
        rebase(observations, keys=bbsr_keys, from_year=2015, to_year=2016, on_unmatched="flga")  # type: ignore[arg-type]


def test_null_source_cell_makes_the_rebased_cell_null_and_is_reported(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    observations = [Observation("03152", 2015, None, "."), Observation("03156", 2015, 73885.0)]
    result = rebase(observations, keys=bbsr_keys, from_year=2015, to_year=2016)
    (row,) = result.rows
    assert (row.value, row.flag, row.sources) == (None, Flag.REBASED, ("03152", "03156"))
    assert [(i.key, i.year) for i in result.issues_of(IssueKind.NULL_INPUT)] == [("03152", 2015)]


# --- direction, sheets, years -----------------------------------------------------------------


def test_direction_is_forward_only(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    with pytest.raises(ValueError, match="forward"):
        rebase([Observation("03152", 2015, 1.0)], keys=bbsr_keys, from_year=2016, to_year=2015)


def test_missing_key_sheet_raises(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    with pytest.raises(RebaseError, match="no key rows for sheet 2014-2015"):
        rebase([Observation("03152", 2014, 1.0)], keys=bbsr_keys, from_year=2014, to_year=2015)


def test_observation_years_inside_the_key_sheets_gap_raise() -> None:
    keys = [_row("01001", "01001", 1.0, from_year=2013, to_year=2016)]
    observations = [Observation("01001", 2014, 1.0), Observation("01001", 2015, 1.0)]
    with pytest.raises(RebaseError, match=r"\[2014, 2015\] fall between"):
        rebase(observations, keys=keys, from_year=2013, to_year=2016)


def test_a_change_on_an_intermediate_sheet_raises(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    # Eisenach is folded into Wartburgkreis on sheet 2020-2021: a 2020 value of 16063 is not on the 2021 Gebietsstand.
    keys = [*bbsr_keys, _row("16063", "16063", 1.0, from_year=2021, to_year=2022)]
    with pytest.raises(RebaseError, match="16063 is not unchanged on sheet 2020-2021 .*receives from 16056"):
        rebase([Observation("16063", 2020, 118000.0)], keys=keys, from_year=2021, to_year=2022)
    # Cochem-Zell is split on sheet 2013-2014: its 2013 value cannot ride a later sheet as if unchanged.
    keys = [*bbsr_keys, _row("07135", "07135", 1.0, from_year=2014, to_year=2015)]
    with pytest.raises(RebaseError, match="07135 is not unchanged on sheet 2013-2014 .*maps onto 07135, 07140"):
        rebase([Observation("07135", 2013, 63202.0)], keys=keys, from_year=2014, to_year=2015)


def test_census_breaks_spanned_by_the_data_are_noted_not_smoothed() -> None:
    keys = [_row("01001", "01001", 1.0, from_year=2011, to_year=2012)]
    observations = [
        Observation("01001", 2010, 100.0),
        Observation("01001", 2011, 90.0),
        Observation("01001", 2012, 91.0),
    ]
    result = rebase(observations, keys=keys, from_year=2011, to_year=2012)
    assert result.census_breaks == (2011,)
    assert [(r.value, r.flag) for r in result.rows] == [
        (100.0, Flag.OBSERVED),
        (90.0, Flag.OBSERVED),
        (91.0, Flag.OBSERVED),
    ]


# --- inputs -----------------------------------------------------------------------------------


def test_observation_rejects_non_kreis_keys_and_bad_values() -> None:
    with pytest.raises(ValueError, match="not a 5-digit Kreis key"):
        Observation("03", 2015, 1.0)
    with pytest.raises(ValueError, match="not a 5-digit Kreis key"):
        Observation("03159016", 2015, 1.0)
    with pytest.raises(TypeError, match="year must be an int"):
        Observation("03159", "2015", 1.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        Observation("03159", 2015, float("nan"))


def test_a_dash_without_a_value_is_a_genuine_zero() -> None:
    assert Observation("03159", 2016, None, "-").value == 0.0
    assert Observation("03159", 2016, None, "-").is_numeric is False


def test_duplicate_observations_raise(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    with pytest.raises(RebaseError, match="03152 2015 appears more than once"):
        rebase([Observation("03152", 2015, 1.0)] * 2, keys=bbsr_keys, from_year=2015, to_year=2016)


def test_share_kind_accepts_wire_strings(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    result = rebase([Observation("03152", 2015, 10.0)], keys=bbsr_keys, from_year=2015, to_year=2016, share="area")
    assert result.edition.share is ShareKind.AREA
    with pytest.raises(ValueError, match="people"):
        rebase([Observation("03152", 2015, 10.0)], keys=bbsr_keys, from_year=2015, to_year=2016, share="people")
