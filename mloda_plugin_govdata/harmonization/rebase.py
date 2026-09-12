"""Re-basing Kreis-level values across a Gebietsstand change with BBSR proportional keys (WP-E).

One explicit key sheet per call, ``from_year`` to ``to_year``, forward as the BBSR file is built.
Observations at or before ``from_year`` are taken to be on the ``from_year`` Gebietsstand and are
re-based onto ``to_year``'s through the chosen share; observations from ``to_year`` on are already
on the target Gebietsstand and pass through as observed. Every output row carries a flag, inputs
are never mutated, and whatever the arithmetic could not use is reported as data.

Validity comes from the key sheet, never from labels: source keys exist at 31.12.``from_year``,
target keys at 31.12.``to_year``. GENESIS writes ``-`` for a Kreis outside its validity; such a
cell is excluded and reported, never summed as 0. A numeric value there contradicts the key file
and raises.

Rounding: none. A count re-based through a fractional share is fractional by construction; values
stay float and totals are conserved up to float error. Round at presentation time.

Standalone: usable without mloda.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from .keys import AgsLevel, detect_level
from .reference.bbsr import UmsteigeschluesselRow
from .reference.sources import BBSR_KREISE, ReferenceSource

# Zensus 2011 and Zensus 2022 re-based the Bevoelkerungsfortschreibung; values on either side of a
# break are not comparable and are never smoothed here, only noted.
CENSUS_BREAKS: tuple[int, ...] = (2011, 2022)
DEFAULT_TOLERANCE = 1e-6
NOT_AVAILABLE_MARKER = "-"


class ShareKind(str, Enum):
    AREA = "area"
    POPULATION = "population"
    EMPLOYEES = "employees"


_SHARE_ATTRIBUTE: dict[ShareKind, str] = {
    ShareKind.AREA: "area_share",
    ShareKind.POPULATION: "population_share",
    ShareKind.EMPLOYEES: "employee_share",
}


class Flag(str, Enum):
    OBSERVED = "observed"
    REBASED = "rebased"


class IssueKind(str, Enum):
    SHARE_SUM = "share_sum"  # an unrequested source key's shares do not sum to 1 (requested keys raise)
    NEGATIVE_SHARE = "negative_share"
    DUPLICATE_PAIR = "duplicate_pair"
    ZERO_SHARE = "zero_share"
    NOT_APPLICABLE = "not_applicable"  # a "-" cell outside its key's validity, excluded
    UNMATCHED = "unmatched"  # key absent from the sheet (on_unmatched="flag")
    NULL_INPUT = "null_input"  # a null source cell; the re-based cell is null too
    UNVERIFIED_YEAR = "unverified_year"  # no sheet given to confirm the key was unchanged that year


class RebaseError(ValueError):
    pass


class ShareSumError(RebaseError):
    def __init__(self, key: str, total: float, sheet: str, share: ShareKind) -> None:
        self.key, self.total, self.sheet, self.share = key, total, sheet, share
        super().__init__(f"{key}: {share.value} shares sum to {total:.7f} on sheet {sheet}, not 1; cannot re-base it")


class ValidityError(RebaseError):
    pass


@dataclass(frozen=True)
class Observation:
    """One Kreis cell: ``marker`` is the raw GENESIS sign (``""`` for a number, ``"-"`` for nichts vorhanden)."""

    key: str
    year: int
    value: float | None
    marker: str = ""

    def __post_init__(self) -> None:
        if detect_level(self.key) != AgsLevel.KREIS:
            raise ValueError(f"{self.key!r} is not a 5-digit Kreis key")
        if isinstance(self.year, bool) or not isinstance(self.year, int):
            raise TypeError(f"year must be an int, got {type(self.year).__name__}")
        if self.value is None and self.marker == NOT_AVAILABLE_MARKER:
            object.__setattr__(self, "value", 0.0)  # "-" is a genuine zero inside the key's validity
        if self.value is not None:
            if isinstance(self.value, bool):
                raise TypeError("value must be a number or None, got bool")
            value = float(self.value)
            if math.isnan(value) or math.isinf(value):
                raise ValueError(f"{self.key} {self.year}: value must be finite or None")
            object.__setattr__(self, "value", value)

    @property
    def is_numeric(self) -> bool:
        return self.value is not None and self.marker == ""


@dataclass(frozen=True)
class KeyEdition:
    source: str
    url: str
    sha256: str | None
    from_year: int
    to_year: int
    share: ShareKind

    @property
    def sheet(self) -> str:
        return f"{self.from_year}-{self.to_year}"


@dataclass(frozen=True)
class RebasedRow:
    key: str
    year: int
    value: float | None
    flag: Flag
    sources: tuple[str, ...]  # contributing source keys, sorted; empty for an observed row
    marker: str = ""  # raw sign of an observed cell; "" once re-based


@dataclass(frozen=True)
class RebaseIssue:
    kind: IssueKind
    key: str
    year: int | None
    detail: str


@dataclass(frozen=True)
class RebaseResult:
    rows: tuple[RebasedRow, ...]
    edition: KeyEdition
    issues: tuple[RebaseIssue, ...]
    census_breaks: tuple[int, ...]  # breaks the observation years span, noted only

    def issues_of(self, kind: IssueKind) -> tuple[RebaseIssue, ...]:
        return tuple(issue for issue in self.issues if issue.kind == kind)


def observations_from_columns(
    keys: Iterable[str], years: Iterable[int], values: Iterable[float | None], markers: Iterable[str]
) -> list[Observation]:
    """Builds observations from parallel columns (e.g. an ffcsv table's key, ``time``, ``value``, ``value_marker``)."""
    return [Observation(k, y, v, m) for k, y, v, m in zip(keys, years, values, markers, strict=True)]


@dataclass(frozen=True)
class _Part:
    source: str
    weight: float
    value: float | None
    marker: str


def _checked(observations: Sequence[Observation]) -> tuple[Observation, ...]:
    if not observations:
        raise RebaseError("no observations given")
    seen: set[tuple[str, int]] = set()
    for obs in observations:
        if (obs.key, obs.year) in seen:
            raise RebaseError(f"observation for {obs.key} {obs.year} appears more than once")
        seen.add((obs.key, obs.year))
    return tuple(observations)


def _share_of(row: UmsteigeschluesselRow, share: ShareKind) -> float:
    return float(getattr(row, _SHARE_ATTRIBUTE[share]))


def _sheet_rows(keys: Sequence[UmsteigeschluesselRow], from_year: int, to_year: int) -> list[UmsteigeschluesselRow]:
    return [row for row in keys if (row.from_year, row.to_year) == (from_year, to_year)]


def _check_sheet(
    sheet: Sequence[UmsteigeschluesselRow], share: ShareKind, requested: set[str], tolerance: float, name: str
) -> tuple[dict[tuple[str, str], float], list[RebaseIssue]]:
    """Share-sum, duplicate-pair, zero- and negative-share checks; raises for requested keys, reports the rest.

    Returns the renormalized weight per (source, target) pair of every requested key.
    """
    issues: list[RebaseIssue] = []
    sums: dict[str, float] = defaultdict(float)
    pairs: dict[tuple[str, str], int] = defaultdict(int)
    for row in sheet:
        value = _share_of(row, share)
        pairs[(row.source_key, row.target_key)] += 1
        sums[row.source_key] += value
        if value < 0:
            detail = f"{row.source_key} -> {row.target_key} carries a negative {share.value} share on sheet {name}"
            if row.source_key in requested:
                raise RebaseError(detail)
            issues.append(RebaseIssue(IssueKind.NEGATIVE_SHARE, row.source_key, None, detail))
        elif value == 0:
            detail = f"{row.source_key} -> {row.target_key} carries a zero {share.value} share on sheet {name}"
            issues.append(RebaseIssue(IssueKind.ZERO_SHARE, row.source_key, None, detail))
    for (source, target), count in pairs.items():
        if count > 1:
            detail = f"{source} -> {target} appears {count} times on sheet {name}"
            if source in requested:
                raise RebaseError(detail)
            issues.append(RebaseIssue(IssueKind.DUPLICATE_PAIR, source, None, detail))
    for source, total in sums.items():
        if abs(total - 1.0) > tolerance:
            if source in requested:
                raise ShareSumError(source, total, name, share)
            detail = f"{source}: {share.value} shares sum to {total:.7f} on sheet {name}, not 1"
            issues.append(RebaseIssue(IssueKind.SHARE_SUM, source, None, detail))
    weights = {
        (row.source_key, row.target_key): _share_of(row, share) / sums[row.source_key]
        for row in sheet
        if row.source_key in requested
    }
    return weights, issues


def _unchanged(sheet: Sequence[UmsteigeschluesselRow], key: str, share: ShareKind, tolerance: float) -> str | None:
    """``None`` when ``key`` maps only onto itself with share 1 and nothing else maps into it, else why not."""
    out = [row for row in sheet if row.source_key == key]
    into = [row for row in sheet if row.target_key == key]
    if not out and not into:
        return "the key is absent from that sheet"
    if len(out) != 1 or out[0].target_key != key or abs(_share_of(out[0], share) - 1.0) > tolerance:
        return "it maps onto " + ", ".join(sorted({row.target_key for row in out}))
    if len(into) != 1:
        return "it receives from " + ", ".join(sorted({row.source_key for row in into if row.source_key != key}))
    return None


def _check_unchanged(
    keys: Sequence[UmsteigeschluesselRow],
    share: ShareKind,
    tolerance: float,
    key_years: dict[str, list[int]],
    from_year: int,
    to_year: int,
) -> list[RebaseIssue]:
    """Requested keys must be unchanged on every sheet between their observation years and the key sheet.

    Raises when a given sheet shows a change; a year with no sheet among ``keys`` is reported as unverified.
    """
    issues: list[RebaseIssue] = []
    for key, years in key_years.items():
        before = range(min(years), from_year)
        after = range(to_year + 1, max(years) + 1)
        for year, (a, b) in [(y, (y, y + 1)) for y in before] + [(y, (y - 1, y)) for y in after]:
            sheet = _sheet_rows(keys, a, b)
            if not sheet:
                detail = f"no key sheet {a}-{b} given; {key} is assumed unchanged at 31.12.{year}"
                issues.append(RebaseIssue(IssueKind.UNVERIFIED_YEAR, key, year, detail))
                continue
            why = _unchanged(sheet, key, share, tolerance)
            if why is not None:
                raise RebaseError(
                    f"{key} is not unchanged on sheet {a}-{b} ({why}); a single key sheet {from_year}-{to_year} "
                    f"cannot re-base its {year} value, re-base sheet by sheet"
                )
    return issues


def rebase(
    observations: Sequence[Observation],
    *,
    keys: Sequence[UmsteigeschluesselRow],
    from_year: int,
    to_year: int,
    share: ShareKind | str = ShareKind.POPULATION,
    tolerance: float = DEFAULT_TOLERANCE,
    on_unmatched: Literal["raise", "drop", "flag"] = "raise",
    source: ReferenceSource = BBSR_KREISE,
) -> RebaseResult:
    """Re-bases Kreis observations onto the ``to_year`` Gebietsstand with the ``from_year``-``to_year`` key sheet.

    ``keys`` may hold more sheets than the one used (e.g. the whole BBSR file); the others verify that
    every requested key was unchanged between its observation years and the key sheet. Shares of the
    requested source keys must sum to 1 within ``tolerance`` (renormalized inside, ``ShareSumError``
    beyond); the rest of the sheet is reported, not raised. ``on_unmatched`` handles keys absent from the
    sheet like ``map_ags_to_nuts``: raise, drop silently, or report.
    """
    share = ShareKind(share)
    if on_unmatched not in ("raise", "drop", "flag"):
        raise ValueError(f"on_unmatched must be 'raise', 'drop', or 'flag', got {on_unmatched!r}")
    if not 0 <= tolerance < 0.5:
        raise ValueError(f"tolerance must be in [0, 0.5), got {tolerance!r}")
    if to_year <= from_year:
        raise ValueError(f"direction is forward: to_year {to_year} must be after from_year {from_year}")
    observations = _checked(observations)
    name = f"{from_year}-{to_year}"
    sheet = _sheet_rows(keys, from_year, to_year)
    if not sheet:
        raise RebaseError(f"no key rows for sheet {name} among the {len(keys)} rows given")
    gap = sorted({obs.year for obs in observations if from_year < obs.year < to_year})
    if gap:
        raise RebaseError(f"observation years {gap} fall between the key sheet's years {name}; no Gebietsstand applies")
    sources = {row.source_key for row in sheet}
    targets = {row.target_key for row in sheet}
    by_source: dict[str, list[UmsteigeschluesselRow]] = defaultdict(list)
    for row in sheet:
        by_source[row.source_key].append(row)

    source_years: dict[str, list[int]] = defaultdict(list)
    target_years: dict[str, list[int]] = defaultdict(list)
    for obs in observations:
        if obs.year <= from_year and obs.key in sources:
            source_years[obs.key].append(obs.year)
        elif obs.year >= to_year and obs.key in targets:
            target_years[obs.key].append(obs.year)
    key_years: dict[str, list[int]] = defaultdict(list)
    for years_by_key in (source_years, target_years):
        for key, years in years_by_key.items():
            key_years[key] += years
    weights, issues = _check_sheet(sheet, share, set(source_years), tolerance, name)
    issues += _check_unchanged(keys, share, tolerance, key_years, from_year, to_year)

    rows: list[RebasedRow] = []
    parts: dict[tuple[str, int], list[_Part]] = defaultdict(list)
    unmatched: list[Observation] = []
    for obs in observations:
        on_source_side = obs.year <= from_year
        valid = sources if on_source_side else targets
        other = targets if on_source_side else sources
        if obs.key in valid:
            if not on_source_side:
                rows.append(RebasedRow(obs.key, obs.year, obs.value, Flag.OBSERVED, (), obs.marker))
                continue
            for row in by_source[obs.key]:
                weight = weights[(obs.key, row.target_key)]
                if weight != 0:
                    parts[(row.target_key, obs.year)].append(_Part(obs.key, weight, obs.value, obs.marker))
        elif obs.key in other:
            side = f"before 31.12.{to_year}" if on_source_side else f"from 31.12.{to_year} on"
            if obs.is_numeric:
                raise ValidityError(
                    f"{obs.key} carries a value for {obs.year} but key sheet {name} says it does not exist {side}"
                )
            detail = f"{obs.key} does not exist {side} per key sheet {name}; its {obs.year} cell ({obs.marker!r}) is excluded"
            issues.append(RebaseIssue(IssueKind.NOT_APPLICABLE, obs.key, obs.year, detail))
        else:
            unmatched.append(obs)

    if unmatched and on_unmatched == "raise":
        listed = ", ".join(sorted({obs.key for obs in unmatched}))
        raise RebaseError(f"key(s) not on key sheet {name}: {listed}")
    if on_unmatched == "flag":
        issues += [
            RebaseIssue(IssueKind.UNMATCHED, obs.key, obs.year, f"{obs.key} is not on key sheet {name}")
            for obs in unmatched
        ]

    for (target, year), contributions in parts.items():
        only = contributions[0]
        if len(contributions) == 1 and only.source == target and only.weight == 1.0:
            rows.append(RebasedRow(target, year, only.value, Flag.OBSERVED, (), only.marker))
            continue
        nulls = [part for part in contributions if part.value is None]
        for part in nulls:
            detail = f"{part.source} {year} is null ({part.marker!r}); the re-based {target} {year} is null"
            issues.append(RebaseIssue(IssueKind.NULL_INPUT, part.source, year, detail))
        value = None if nulls else sum(part.weight * (part.value or 0.0) for part in contributions)
        contributing = tuple(sorted({part.source for part in contributions}))
        rows.append(RebasedRow(target, year, value, Flag.REBASED, contributing))

    observed_years = [obs.year for obs in observations]
    breaks = tuple(b for b in CENSUS_BREAKS if min(observed_years) < b <= max(observed_years))
    edition = KeyEdition(source.name, source.url, source.sha256, from_year, to_year, share)
    rows.sort(key=lambda row: (row.year, row.key))
    return RebaseResult(tuple(rows), edition, tuple(issues), breaks)
