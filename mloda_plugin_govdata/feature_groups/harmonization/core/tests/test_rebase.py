import csv
from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from mloda_plugin_govdata.feature_groups.destatis.core.parse import parse_ffcsv_zip
from mloda_plugin_govdata.feature_groups.harmonization.core.rebase import (
    DEFAULT_TOLERANCE,
    Flag,
    IncompleteError,
    IssueKind,
    KeySheet,
    Observation,
    RebasedRow,
    RebaseError,
    RebaseResult,
    ShareKind,
    ShareSumError,
    ValidityError,
    observations_from_columns,
    rebase,
)
from mloda_plugin_govdata.feature_groups.harmonization.core.reference.bbsr import (
    UmsteigeschluesselRow,
    parse_bbsr_kreise_workbook,
)
from mloda_plugin_govdata.feature_groups.harmonization.core.reference.sources import BBSR_KREISE, ReferenceSource

GOETTINGEN_ZIP = "12411-0015_2013-2017_de_flat.zip"
COCHEM_ZELL_ZIP = "12411-0015_2013-2014_de_flat.zip"

# The fixture is an extract, so its key sheet names the extract's own hash (see the reference NOTICE).
EXTRACT = ReferenceSource(
    name="BBSR Umsteigeschluessel Kreise (test extract)",
    url=BBSR_KREISE.url,
    sha256="5784d7da0cffc2f0643529531bafa34a764753202955c3b35dbf5335a3e47fb0",
    license=BBSR_KREISE.license,
    attribution=BBSR_KREISE.attribution,
)
SYNTHETIC = ReferenceSource(name="synthetic keys", url="test://keys", sha256=None, license="n/a", attribution="n/a")


def _row(
    source: str, target: str, share: float, *, from_year: int = 2015, to_year: int = 2016
) -> UmsteigeschluesselRow:
    return UmsteigeschluesselRow(from_year, to_year, source, source, share, share, share, 0.0, 0.0, 0.0, target, target)


def _rebase(observations: list[Observation], keys: list[UmsteigeschluesselRow], **kwargs: Any) -> RebaseResult:
    kwargs.setdefault("source", SYNTHETIC)
    kwargs.setdefault("from_year", 2015)
    kwargs.setdefault("to_year", 2016)
    return rebase(observations, keys=keys, **kwargs)


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


def _snapshot(observations: list[Observation]) -> list[tuple[str, int, float | None, str]]:
    return [(o.key, o.year, o.value, o.marker) for o in observations]


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
    result = _rebase(goettingen, bbsr_keys, source=EXTRACT, share="population")

    assert _cells(result.rows) == _expected(fixtures_dir / "c2-goettingen-2016.csv")
    # Merger shares are exactly 1, so the re-based sums are exact, not merely rounded.
    assert [r.value for r in result.rows] == [322616.0, 324013.0, 329538.0, 327065.0, 328036.0]
    assert [r.marker for r in result.rows] == [""] * 5
    assert result.key_sheet == KeySheet(EXTRACT.name, EXTRACT.url, EXTRACT.sha256, 2015, 2016, ShareKind.POPULATION)
    assert result.key_sheet.sheet == "2015-2016"
    assert result.census_breaks == ()
    assert result.issues_of(IssueKind.RENORMALIZED) == ()


def test_dash_cells_outside_validity_are_excluded_and_reported_never_summed(
    goettingen: list[Observation], bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    result = _rebase(goettingen, bbsr_keys)
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
    assert result.issues_of(IssueKind.ZERO_MARKER) == ()


def test_known_stale_share_defect_is_tolerated_for_unrequested_keys_and_named(
    goettingen: list[Observation], bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    result = _rebase(goettingen, bbsr_keys)
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
        _rebase([Observation("07135", 2015, 62400.0)], bbsr_keys)


def test_missing_intermediate_sheets_are_reported_as_unverified(
    goettingen: list[Observation], bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    # The extract has no 2014-2015 and no 2016-2017 sheet, so those years cannot be confirmed unchanged.
    result = _rebase(goettingen, bbsr_keys)
    unverified = {(i.key, i.year) for i in result.issues_of(IssueKind.UNVERIFIED_YEAR)}
    assert unverified == {("03152", 2014), ("03156", 2014), ("03159", 2017)}

    identity = [
        _row("03152", "03152", 1.0, from_year=2014, to_year=2015),
        _row("03156", "03156", 1.0, from_year=2014, to_year=2015),
        _row("03159", "03159", 1.0, from_year=2016, to_year=2017),
    ]
    complete = _rebase(goettingen, [*bbsr_keys, *identity])
    assert complete.issues_of(IssueKind.UNVERIFIED_YEAR) == ()
    assert complete.rows == result.rows


# --- the fractional case ----------------------------------------------------------------------


def test_fractional_case_matches_the_expected_values_to_the_integer(
    fixtures_dir: Path, ffcsv_fixtures_dir: Path, bbsr_keys: list[UmsteigeschluesselRow]
) -> None:
    observations = _ffcsv_observations(ffcsv_fixtures_dir / COCHEM_ZELL_ZIP)
    inputs = _snapshot(observations)
    result = _rebase(observations, bbsr_keys, source=EXTRACT, from_year=2013, to_year=2014)

    assert _cells(result.rows) == _expected(fixtures_dir / "c2-cochem-zell-2014.csv")
    values = {(r.key, r.year): r.value for r in result.rows}
    stays = values[("07135", 2013)]
    moved = (values[("07140", 2013)] or 0) - 100770
    assert stays == pytest.approx(62118, abs=1e-6)
    assert moved == pytest.approx(1084, abs=1e-6)
    assert (stays or 0) + moved == pytest.approx(63202, abs=1e-6)  # totals conserved; nothing rounded
    assert _snapshot(observations) == inputs  # inputs are never mutated; the observed 100,770 lives only there
    assert result.issues == ()


# --- share-sum check, duplicates, zero and invalid shares --------------------------------------


def test_share_sum_beyond_tolerance_raises_for_requested_keys_only() -> None:
    keys = [
        _row("01001", "01001", 0.6),
        _row("01001", "01002", 0.3),
        _row("01002", "01002", 1.0),
        _row("01003", "01003", 0.5),
    ]
    with pytest.raises(ShareSumError, match="01001: population shares sum to 0.9000000"):
        _rebase([Observation("01001", 2015, 100.0)], keys)
    result = _rebase([Observation("01002", 2015, 100.0)], keys, on_incomplete="flag")
    assert {i.key for i in result.issues_of(IssueKind.SHARE_SUM)} == {"01001", "01003"}


def test_share_sum_inside_tolerance_is_renormalized_reported_and_conserves_totals() -> None:
    keys = [_row("01001", "01001", 0.5), _row("01001", "01002", 0.5000004)]
    observations = [Observation("01001", 2015, 1000.0)]
    result = _rebase(observations, keys, tolerance=1e-6)
    values = {r.key: r.value or 0 for r in result.rows}
    assert values["01001"] + values["01002"] == pytest.approx(1000.0, abs=1e-9)
    assert values["01001"] == pytest.approx(1000 * 0.5 / 1.0000004)
    (renormalized,) = result.issues_of(IssueKind.RENORMALIZED)
    assert (renormalized.key, "1.0000004" in renormalized.detail) == ("01001", True)
    with pytest.raises(ShareSumError):
        _rebase(observations, keys, tolerance=1e-7)


def test_tolerance_cannot_absorb_a_defective_sheet() -> None:
    with pytest.raises(ValueError, match="tolerance must be in"):
        _rebase([Observation("01001", 2015, 1.0)], [_row("01001", "01001", 1.0)], tolerance=0.02)


def test_duplicate_pair_raises_for_requested_keys_and_is_reported_otherwise() -> None:
    keys = [_row("01001", "01002", 0.5), _row("01001", "01002", 0.5), _row("01002", "01002", 1.0)]
    with pytest.raises(RebaseError, match="01001 -> 01002 appears 2 times"):
        _rebase([Observation("01001", 2015, 1.0)], keys)
    result = _rebase([Observation("01002", 2015, 1.0)], keys, on_incomplete="flag")
    assert [i.key for i in result.issues_of(IssueKind.DUPLICATE_PAIR)] == ["01001"]


def test_zero_share_rows_are_reported_and_contribute_nothing() -> None:
    keys = [_row("01001", "01001", 1.0), _row("01001", "01002", 0.0), _row("01002", "01002", 1.0)]
    observations = [Observation("01001", 2015, 10.0), Observation("01002", 2015, 20.0)]
    result = _rebase(observations, keys)
    assert [(i.key, "01001 -> 01002" in i.detail) for i in result.issues_of(IssueKind.ZERO_SHARE)] == [("01001", True)]
    rows = {r.key: r for r in result.rows}
    assert (rows["01002"].value, rows["01002"].flag, rows["01002"].sources) == (20.0, Flag.OBSERVED, ())


@pytest.mark.parametrize(
    ("bad", "kind"), [(-0.2, "negative"), (float("nan"), "non-finite"), (float("inf"), "non-finite")]
)
def test_invalid_shares_raise_for_requested_keys_and_are_reported_otherwise(bad: float, kind: str) -> None:
    # A NaN share passes both `< 0` and the share-sum comparison, so it needs its own check.
    keys = [_row("01001", "01001", 1.2), _row("01001", "01002", bad), _row("01002", "01002", 1.0)]
    with pytest.raises(RebaseError, match=f"{kind} population share"):
        _rebase([Observation("01001", 2015, 1.0)], keys)
    result = _rebase([Observation("01002", 2015, 1.0)], keys, on_incomplete="flag")
    assert [(i.key, kind in i.detail) for i in result.issues_of(IssueKind.INVALID_SHARE)] == [("01001", True)]
    assert all(r.value is None or r.value == r.value for r in result.rows)  # never NaN


@given(
    weights=st.lists(st.floats(min_value=0.01, max_value=1.0), min_size=1, max_size=5),
    value=st.floats(min_value=0.0, max_value=1e8),
)
def test_rebasing_conserves_the_total_and_scales_each_target_by_its_share(weights: list[float], value: float) -> None:
    total = sum(weights)
    shares = [w / total for w in weights]
    targets = [f"0100{i}" for i in range(len(shares))]
    keys = [_row("01001", target, share) for target, share in zip(targets, shares)]
    result = _rebase([Observation("01001", 2015, value)], keys)
    values = {r.key: r.value or 0 for r in result.rows}
    assert sum(values.values()) == pytest.approx(value, rel=1e-9, abs=1e-6)
    for target, share in zip(targets, shares):
        assert values[target] == pytest.approx(value * share, rel=1e-9, abs=1e-6)


@given(delta=st.floats(min_value=-0.009, max_value=0.009).filter(lambda d: abs(d) > 1e-9))
def test_share_sums_off_by_more_than_the_tolerance_raise_and_inside_it_renormalize(delta: float) -> None:
    assume(abs(abs(delta) - DEFAULT_TOLERANCE) > 1e-9)  # float error at the exact boundary is not the property
    keys = [_row("01001", "01001", 0.5), _row("01001", "01002", 0.5 + delta)]
    observations = [Observation("01001", 2015, 1000.0)]
    if abs(delta) > DEFAULT_TOLERANCE:
        with pytest.raises(ShareSumError):
            _rebase(observations, keys)
    else:
        strict = _rebase(observations, keys)
        assert sum(r.value or 0 for r in strict.rows) == pytest.approx(1000.0)
    loose = _rebase(observations, keys, tolerance=0.01)
    assert sum(r.value or 0 for r in loose.rows) == pytest.approx(1000.0)
    assert len(loose.issues_of(IssueKind.RENORMALIZED)) == 1


# --- validity, unmatched keys, incomplete targets, null inputs ----------------------------------


def test_numeric_value_outside_validity_raises(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    with pytest.raises(ValidityError, match="03159 carries a value for 2015 .* does not exist before 31.12.2016"):
        _rebase([Observation("03159", 2015, 1.0)], bbsr_keys)
    with pytest.raises(ValidityError, match="03152 carries a value for 2016 .* does not exist from 31.12.2016 on"):
        _rebase([Observation("03152", 2016, 1.0)], bbsr_keys)
    with pytest.raises(ValidityError):  # a numeric 0 is not a "-" cell
        _rebase([Observation("03159", 2015, 0.0)], bbsr_keys)


def test_observed_pass_through_keeps_the_raw_marker(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    observations = [Observation("03159", 2016, 0.0, "-"), Observation("03159", 2017, None, ".")]
    result = _rebase(observations, bbsr_keys)
    assert [(r.value, r.marker, r.flag) for r in result.rows] == [(0.0, "-", Flag.OBSERVED), (None, ".", Flag.OBSERVED)]


def test_a_dash_cell_inside_validity_entering_a_sum_is_reported(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    # The sheet cannot adjudicate a 2013 "-" cell of 03152; it is taken as 0 and said so.
    observations = [Observation("03152", 2013, 0.0, "-"), Observation("03156", 2013, 74367.0)]
    result = _rebase(observations, bbsr_keys)
    (row,) = result.rows
    assert (row.value, row.sources) == (74367.0, ("03152", "03156"))
    assert [(i.key, i.year) for i in result.issues_of(IssueKind.ZERO_MARKER)] == [("03152", 2013)]


def test_unmatched_keys_follow_the_on_unmatched_policy(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    observations = [Observation("03152", 2015, 5.0), Observation("03156", 2015, 7.0), Observation("09999", 2015, 1.0)]
    with pytest.raises(RebaseError, match="not on key sheet 2015-2016: 09999"):
        _rebase(observations, bbsr_keys)
    flagged = _rebase(observations, bbsr_keys, on_unmatched="flag")
    assert [(i.key, i.year) for i in flagged.issues_of(IssueKind.UNMATCHED)] == [("09999", 2015)]
    dropped = _rebase(observations, bbsr_keys, on_unmatched="drop")
    assert dropped.issues_of(IssueKind.UNMATCHED) == ()
    assert [(r.key, r.value, r.sources) for r in dropped.rows] == [("03159", 12.0, ("03152", "03156"))]
    with pytest.raises(ValueError, match="on_unmatched must be"):
        _rebase(observations, bbsr_keys, on_unmatched="flga")


def test_a_target_fed_by_an_unobserved_key_follows_the_on_incomplete_policy(
    bbsr_keys: list[UmsteigeschluesselRow],
) -> None:
    # Only one of the two Kreise merging into 03159 is given: a partial sum must not pose as its population.
    observations = [Observation("03152", 2015, 255653.0)]
    with pytest.raises(IncompleteError, match="03159 2015 is missing 03156"):
        _rebase(observations, bbsr_keys)
    flagged = _rebase(observations, bbsr_keys, on_incomplete="flag")
    (row,) = flagged.rows
    assert (row.value, row.flag, row.sources) == (None, Flag.REBASED, ("03152",))
    assert [(i.key, i.year) for i in flagged.issues_of(IssueKind.MISSING_SOURCE)] == [("03156", 2015)]
    dropped = _rebase(observations, bbsr_keys, on_incomplete="drop")
    assert dropped.rows == ()
    with pytest.raises(ValueError, match="on_incomplete must be"):
        _rebase(observations, bbsr_keys, on_incomplete="flga")


def test_the_absorbing_key_alone_is_never_flagged_observed(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    # Wartburgkreis 16063 absorbs Eisenach 16056 on sheet 2020-2021; its own 2020 value is not the 2021 Kreis.
    observations = [Observation("16063", 2020, 118000.0)]
    with pytest.raises(IncompleteError, match="16063 2020 is missing 16056"):
        _rebase(observations, bbsr_keys, from_year=2020, to_year=2021)
    flagged = _rebase(observations, bbsr_keys, from_year=2020, to_year=2021, on_incomplete="flag")
    assert [(r.value, r.flag, r.sources) for r in flagged.rows] == [(None, Flag.REBASED, ("16063",))]
    both = _rebase([*observations, Observation("16056", 2020, 42000.0)], bbsr_keys, from_year=2020, to_year=2021)
    assert [(r.value, r.flag, r.sources) for r in both.rows] == [(160000.0, Flag.REBASED, ("16056", "16063"))]


def test_null_source_cell_makes_the_rebased_cell_null_and_is_reported(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    observations = [Observation("03152", 2015, None, "."), Observation("03156", 2015, 73885.0)]
    result = _rebase(observations, bbsr_keys)
    (row,) = result.rows
    assert (row.value, row.flag, row.sources) == (None, Flag.REBASED, ("03152", "03156"))
    assert [(i.key, i.year) for i in result.issues_of(IssueKind.NULL_INPUT)] == [("03152", 2015)]


# --- direction, sheets, years -----------------------------------------------------------------


def test_direction_is_forward_only(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    with pytest.raises(ValueError, match="forward"):
        _rebase([Observation("03152", 2015, 1.0)], bbsr_keys, from_year=2016, to_year=2015)


def test_missing_key_sheet_raises(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    with pytest.raises(RebaseError, match="no key rows for sheet 2014-2015"):
        _rebase([Observation("03152", 2014, 1.0)], bbsr_keys, from_year=2014, to_year=2015)


def test_observation_years_inside_the_key_sheets_gap_raise() -> None:
    keys = [_row("01001", "01001", 1.0, from_year=2013, to_year=2016)]
    observations = [Observation("01001", 2014, 1.0), Observation("01001", 2015, 1.0)]
    with pytest.raises(RebaseError, match=r"\[2014, 2015\] fall between"):
        _rebase(observations, keys, from_year=2013, to_year=2016)


def test_a_change_on_an_intermediate_sheet_raises(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    # Eisenach is folded into Wartburgkreis on sheet 2020-2021: a 2020 value of 16063 is not on the 2021 Gebietsstand.
    keys = [*bbsr_keys, _row("16063", "16063", 1.0, from_year=2021, to_year=2022)]
    with pytest.raises(RebaseError, match="16063 is not unchanged on sheet 2020-2021 .*receives from 16056"):
        _rebase([Observation("16063", 2020, 118000.0)], keys, from_year=2021, to_year=2022)
    # Cochem-Zell is split on sheet 2013-2014: its 2013 value cannot ride a later sheet as if unchanged.
    keys = [*bbsr_keys, _row("07135", "07135", 1.0, from_year=2014, to_year=2015)]
    with pytest.raises(RebaseError, match="07135 is not unchanged on sheet 2013-2014 .*maps onto 07135, 07140"):
        _rebase([Observation("07135", 2013, 63202.0)], keys, from_year=2014, to_year=2015)
    # The stale identity share on sheet 2015-2016 is named as such, not as "maps onto itself".
    keys = [*bbsr_keys, _row("07135", "07135", 1.0, from_year=2016, to_year=2017)]
    with pytest.raises(RebaseError, match="07135 is not unchanged on sheet 2015-2016 .*identity share is 0.9828486"):
        _rebase([Observation("07135", 2015, 62400.0)], keys, from_year=2016, to_year=2017)
    # A key absent from a given intermediate sheet is a change too, not silently unverified.
    keys = [_row("01001", "01001", 1.0), _row("01002", "01002", 1.0, from_year=2014, to_year=2015)]
    with pytest.raises(RebaseError, match="01001 is not unchanged on sheet 2014-2015 .*absent"):
        _rebase([Observation("01001", 2014, 1.0)], keys)


def test_a_zero_share_row_on_an_intermediate_sheet_does_not_count_as_a_change() -> None:
    keys = [
        _row("01001", "01001", 1.0),
        _row("01001", "01001", 1.0, from_year=2014, to_year=2015),
        _row("01001", "01002", 0.0, from_year=2014, to_year=2015),
    ]
    result = _rebase([Observation("01001", 2014, 100.0)], keys)
    assert [(r.key, r.value, r.flag) for r in result.rows] == [("01001", 100.0, Flag.OBSERVED)]
    assert result.issues_of(IssueKind.UNVERIFIED_YEAR) == ()


@pytest.mark.parametrize(
    ("years", "breaks"), [((2010, 2011, 2012), (2011,)), ((2011, 2012), ()), ((2021, 2022), (2022,))]
)
def test_census_breaks_spanned_by_the_data_are_noted_not_smoothed(
    years: tuple[int, ...], breaks: tuple[int, ...]
) -> None:
    keys = [_row("01001", "01001", 1.0, from_year=years[-1], to_year=years[-1] + 1)]
    observations = [Observation("01001", year, 100.0 + year) for year in years]
    result = _rebase(observations, keys, from_year=years[-1], to_year=years[-1] + 1)
    assert result.census_breaks == breaks
    assert [(r.value, r.flag) for r in result.rows] == [(100.0 + year, Flag.OBSERVED) for year in years]


# --- inputs -----------------------------------------------------------------------------------


def test_observation_rejects_non_kreis_keys_and_bad_values() -> None:
    with pytest.raises(ValueError, match="not a 5-digit Kreis key"):
        Observation("03", 2015, 1.0)
    with pytest.raises(ValueError, match="not a 5-digit Kreis key"):
        Observation("03159016", 2015, 1.0)
    with pytest.raises(TypeError, match="year must be an int"):
        Observation("03159", "2015", 1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="value must be a number"):
        Observation("03159", 2015, "5")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        Observation("03159", 2015, float("nan"))


def test_a_dash_without_a_value_is_a_genuine_zero() -> None:
    assert Observation("03159", 2016, None, "-").value == 0.0
    assert Observation("03159", 2016, None, "-").is_numeric is False


def test_duplicate_observations_raise(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    with pytest.raises(RebaseError, match="03152 2015 appears more than once"):
        _rebase([Observation("03152", 2015, 1.0)] * 2, bbsr_keys)


def test_a_sheet_without_employee_columns_refuses_the_employees_share() -> None:
    early = UmsteigeschluesselRow(2015, 2016, "01001", "x", 1.0, 1.0, None, 0.0, 0.0, None, "01001", "x")
    assert _rebase([Observation("01001", 2015, 1.0)], [early], share="area").rows[0].value == 1.0
    with pytest.raises(RebaseError, match="carries no employees share"):
        _rebase([Observation("01001", 2015, 1.0)], [early], share="employees")


def test_share_kind_accepts_wire_strings(bbsr_keys: list[UmsteigeschluesselRow]) -> None:
    observations = [Observation("03152", 2015, 10.0), Observation("03156", 2015, 1.0)]
    result = _rebase(observations, bbsr_keys, share="area")
    assert result.key_sheet.share is ShareKind.AREA
    with pytest.raises(ValueError, match="people"):
        _rebase(observations, bbsr_keys, share="people")
