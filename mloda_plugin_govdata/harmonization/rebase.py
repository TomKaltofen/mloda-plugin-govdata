"""Re-basing Kreis-level values across a Gebietsstand change with BBSR proportional keys.

One explicit key sheet per call, ``from_year`` to ``to_year``, forward as the BBSR file is built.
Observations at or before ``from_year`` are taken to be on the ``from_year`` Gebietsstand and are
re-based onto ``to_year``'s through the chosen share; observations from ``to_year`` on are already
on the target Gebietsstand and pass through as observed. Every output row carries a flag, inputs
are never mutated, and whatever the arithmetic could not use is reported as data.

Validity comes from the key sheet, never from labels: source keys exist at 31.12.``from_year``,
target keys at 31.12.``to_year``. GENESIS writes ``-`` for a Kreis outside its validity; at those
two Stichtage such a cell is excluded and reported, never summed as 0, and a numeric value there
contradicts the key file and raises. At earlier or later Stichtage the sheet cannot adjudicate a
``-`` cell, so one that enters a re-based sum is taken as 0 and reported.

Rounding: none. A count re-based through a fractional share is fractional by construction; values
stay float and totals are conserved up to float error. Round at presentation time.

Standalone: usable without mloda.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .keys import AgsLevel, detect_level
from .reference.bbsr import UmsteigeschluesselRow
from .reference.sources import ReferenceSource

# Zensus 2011 and Zensus 2022 re-based the Bevoelkerungsfortschreibung; values on either side of a
# break are not comparable and are never smoothed here, only noted.
CENSUS_BREAKS: tuple[int, ...] = (2011, 2022)
DEFAULT_TOLERANCE = 1e-6
MAX_TOLERANCE = 1e-2  # renormalization repairs rounding noise, never a defective sheet
FLOAT_NOISE = 1e-9  # below this a share sum counts as exactly 1
NOT_AVAILABLE_MARKER = "-"

Policy = Literal["raise", "drop", "flag"]
_POLICIES: tuple[str, ...] = ("raise", "drop", "flag")


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
    RENORMALIZED = "renormalized"  # a requested key's shares were off by more than float noise, inside the tolerance
    INVALID_SHARE = "invalid_share"  # negative or non-finite share on an unrequested key (requested keys raise)
    DUPLICATE_PAIR = "duplicate_pair"
    ZERO_SHARE = "zero_share"
    NOT_APPLICABLE = "not_applicable"  # a "-" cell outside its key's validity, excluded
    ZERO_MARKER = "zero_marker"  # a "-" cell inside validity taken as 0 in a re-based sum
    UNMATCHED = "unmatched"  # key absent from the sheet (on_unmatched="flag")
    NULL_INPUT = "null_input"  # a null source cell; the re-based cell is null too
    MISSING_SOURCE = "missing_source"  # a feeding key has no observation (on_incomplete="flag"); the cell is null
    UNVERIFIED_YEAR = "unverified_year"  # no sheet given to confirm the key was unchanged that year


class RebaseError(ValueError):
    pass


class ShareSumError(RebaseError):
    def __init__(self, key: str, total: float, sheet: str, share: ShareKind) -> None:
        self.key, self.total, self.sheet, self.share = key, total, sheet, share
        super().__init__(f"{key}: {share.value} shares sum to {total:.7f} on sheet {sheet}, not 1; cannot re-base it")


class ValidityError(RebaseError):
    pass


class IncompleteError(RebaseError):
    """A target's feeding keys are not all among the observations, so its re-based value would be a partial sum."""


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
            if isinstance(self.value, (bool, str, bytes)):
                raise TypeError(f"value must be a number or None, got {type(self.value).__name__}")
            value = float(self.value)
            if not math.isfinite(value):
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
    target: str | None = None  # the re-based key the issue affects, when the key itself is a feeder


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


@dataclass
class _Sheet:
    name: str
    rows: list[UmsteigeschluesselRow] = field(default_factory=list)
    by_source: dict[str, list[UmsteigeschluesselRow]] = field(default_factory=lambda: defaultdict(list))
    by_target: dict[str, list[UmsteigeschluesselRow]] = field(default_factory=lambda: defaultdict(list))

    def feeders(self, target: str, share: ShareKind) -> set[str]:
        """Source keys that move anything into ``target``; a zero-share row moves nothing."""
        return {row.source_key for row in self.by_target.get(target, []) if _share_of(row, share) != 0}


def _index(keys: Sequence[UmsteigeschluesselRow]) -> dict[tuple[int, int], _Sheet]:
    sheets: dict[tuple[int, int], _Sheet] = {}
    for row in keys:
        pair = (row.from_year, row.to_year)
        sheet = sheets.get(pair)
        if sheet is None:
            sheet = sheets[pair] = _Sheet(f"{row.from_year}-{row.to_year}")
        sheet.rows.append(row)
        sheet.by_source[row.source_key].append(row)
        sheet.by_target[row.target_key].append(row)
    return sheets


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
    value = getattr(row, _SHARE_ATTRIBUTE[share])
    if value is None:
        raise RebaseError(
            f"sheet {row.from_year}-{row.to_year} carries no {share.value} share (early sheets have none)"
        )
    return float(value)


def _check_sheet(
    sheet: _Sheet, share: ShareKind, requested: set[str], tolerance: float
) -> tuple[dict[tuple[str, str], float], list[RebaseIssue]]:
    """Share-sum, duplicate-pair, zero- and invalid-share checks; raises for requested keys, reports the rest.

    Returns the renormalized weight per (source, target) pair of every requested key.
    """
    issues: list[RebaseIssue] = []
    sums: dict[str, float] = defaultdict(float)
    pairs: dict[tuple[str, str], int] = defaultdict(int)
    for row in sheet.rows:
        value = _share_of(row, share)
        pairs[(row.source_key, row.target_key)] += 1
        sums[row.source_key] += value
        if not math.isfinite(value) or value < 0:
            kind = "non-finite" if not math.isfinite(value) else "negative"
            detail = f"{row.source_key} -> {row.target_key} carries a {kind} {share.value} share on sheet {sheet.name}"
            if row.source_key in requested:
                raise RebaseError(detail)
            issues.append(RebaseIssue(IssueKind.INVALID_SHARE, row.source_key, None, detail))
        elif value == 0:
            detail = f"{row.source_key} -> {row.target_key} carries a zero {share.value} share on sheet {sheet.name}"
            issues.append(RebaseIssue(IssueKind.ZERO_SHARE, row.source_key, None, detail))
    for (source, target), count in pairs.items():
        if count > 1:
            detail = f"{source} -> {target} appears {count} times on sheet {sheet.name}"
            if source in requested:
                raise RebaseError(detail)
            issues.append(RebaseIssue(IssueKind.DUPLICATE_PAIR, source, None, detail))
    for source, total in sums.items():
        if abs(total - 1.0) > tolerance:
            if source in requested:
                raise ShareSumError(source, total, sheet.name, share)
            detail = f"{source}: {share.value} shares sum to {total:.7f} on sheet {sheet.name}, not 1"
            issues.append(RebaseIssue(IssueKind.SHARE_SUM, source, None, detail))
        elif source in requested and abs(total - 1.0) > FLOAT_NOISE:
            detail = f"{source}: {share.value} shares sum to {total:.7f} on sheet {sheet.name}; renormalized to 1"
            issues.append(RebaseIssue(IssueKind.RENORMALIZED, source, None, detail))
    weights = {
        (row.source_key, row.target_key): _share_of(row, share) / sums[row.source_key]
        for row in sheet.rows
        if row.source_key in requested
    }
    return weights, issues


def _unchanged(sheet: _Sheet, key: str, share: ShareKind, tolerance: float) -> str | None:
    """``None`` when ``key`` maps only onto itself with share 1 and nothing else maps into it, else why not.

    Zero-share rows move nothing and are ignored, as in the arithmetic itself.
    """
    out = [row for row in sheet.by_source.get(key, []) if _share_of(row, share) != 0]
    into = [row for row in sheet.by_target.get(key, []) if _share_of(row, share) != 0]
    if any(not math.isfinite(_share_of(row, share)) for row in out + into):
        return "it carries a non-finite share"
    if not out and not into:
        return "the key is absent from that sheet"
    if len(out) == 1 and out[0].target_key == key and abs(_share_of(out[0], share) - 1.0) > tolerance:
        return f"its identity share is {_share_of(out[0], share):.7f}, not 1"
    if len(out) != 1 or out[0].target_key != key:
        return "it maps onto " + ", ".join(sorted({row.target_key for row in out}))
    if len(into) != 1:
        return "it receives from " + ", ".join(sorted({row.source_key for row in into if row.source_key != key}))
    return None


def _check_unchanged(
    sheets: dict[tuple[int, int], _Sheet],
    share: ShareKind,
    tolerance: float,
    key_years: dict[str, list[int]],
    from_year: int,
    to_year: int,
) -> list[RebaseIssue]:
    """Requested keys must be unchanged on every sheet between their observation years and the key sheet.

    Raises when a given sheet shows a change; a year with no sheet among the keys is reported as unverified.
    """
    issues: list[RebaseIssue] = []
    for key, years in key_years.items():
        before = [(year, (year, year + 1)) for year in range(min(years), from_year)]
        after = [(year, (year - 1, year)) for year in range(to_year + 1, max(years) + 1)]
        for year, pair in before + after:
            sheet = sheets.get(pair)
            if sheet is None:
                detail = f"no key sheet {pair[0]}-{pair[1]} given; {key} is assumed unchanged at 31.12.{year}"
                issues.append(RebaseIssue(IssueKind.UNVERIFIED_YEAR, key, year, detail))
                continue
            why = _unchanged(sheet, key, share, tolerance)
            if why is not None:
                raise RebaseError(
                    f"{key} is not unchanged on sheet {sheet.name} ({why}); a single key sheet {from_year}-{to_year} "
                    f"cannot re-base its {year} value, re-base sheet by sheet"
                )
    return issues


def _policy(name: str, value: str) -> None:
    if value not in _POLICIES:
        raise ValueError(f"{name} must be 'raise', 'drop', or 'flag', got {value!r}")


def rebase(
    observations: Sequence[Observation],
    *,
    keys: Sequence[UmsteigeschluesselRow],
    source: ReferenceSource,
    from_year: int,
    to_year: int,
    share: ShareKind | str = ShareKind.POPULATION,
    tolerance: float = DEFAULT_TOLERANCE,
    on_unmatched: Policy = "raise",
    on_incomplete: Policy = "raise",
) -> RebaseResult:
    """Re-bases Kreis observations onto the ``to_year`` Gebietsstand with the ``from_year``-``to_year`` key sheet.

    ``source`` names the file ``keys`` were parsed from and is recorded in the result's edition, not
    verified: pass ``BBSR_KREISE`` for rows from ``load_bbsr_kreise``, which pins that file's sha256.
    ``keys`` may hold more sheets than the one used (e.g. the whole BBSR file); the others verify that
    every requested key was unchanged between its observation years and the key sheet. Shares of the
    requested source keys must sum to 1 within ``tolerance`` (renormalized inside, ``ShareSumError``
    beyond); the rest of the sheet is reported, not raised. ``on_unmatched`` handles keys absent from
    the sheet, ``on_incomplete`` a target whose feeding keys are not all observed (a partial sum):
    raise, drop the row silently, or report (an incomplete target's value is then null).
    """
    share = ShareKind(share)
    _policy("on_unmatched", on_unmatched)
    _policy("on_incomplete", on_incomplete)
    if not 0 <= tolerance <= MAX_TOLERANCE:
        raise ValueError(f"tolerance must be in [0, {MAX_TOLERANCE}], got {tolerance!r}")
    if to_year <= from_year:
        raise ValueError(f"direction is forward: to_year {to_year} must be after from_year {from_year}")
    observations = _checked(observations)
    sheets = _index(keys)
    sheet = sheets.get((from_year, to_year))
    if sheet is None:
        raise RebaseError(f"no key rows for sheet {from_year}-{to_year} among the {len(keys)} rows given")
    gap = sorted({obs.year for obs in observations if from_year < obs.year < to_year})
    if gap:
        raise RebaseError(
            f"observation years {gap} fall between the key sheet's years {sheet.name}; no Gebietsstand applies"
        )

    key_years: dict[str, list[int]] = defaultdict(list)
    requested: set[str] = set()
    for obs in observations:
        if obs.year <= from_year and obs.key in sheet.by_source:
            requested.add(obs.key)
            key_years[obs.key].append(obs.year)
        elif obs.year >= to_year and obs.key in sheet.by_target:
            key_years[obs.key].append(obs.year)
    weights, issues = _check_sheet(sheet, share, requested, tolerance)
    issues += _check_unchanged(sheets, share, tolerance, key_years, from_year, to_year)

    rows: list[RebasedRow] = []
    parts: dict[tuple[str, int], list[_Part]] = defaultdict(list)
    unmatched: list[Observation] = []
    for obs in observations:
        on_source_side = obs.year <= from_year
        valid = sheet.by_source if on_source_side else sheet.by_target
        other = sheet.by_target if on_source_side else sheet.by_source
        if obs.key in valid:
            if not on_source_side:
                rows.append(RebasedRow(obs.key, obs.year, obs.value, Flag.OBSERVED, (), obs.marker))
                continue
            for row in sheet.by_source[obs.key]:
                weight = weights[(obs.key, row.target_key)]
                if weight != 0:
                    parts[(row.target_key, obs.year)].append(_Part(obs.key, weight, obs.value, obs.marker))
        elif obs.key in other:
            side = f"before 31.12.{to_year}" if on_source_side else f"from 31.12.{to_year} on"
            if obs.is_numeric:
                raise ValidityError(
                    f"{obs.key} carries a value for {obs.year} but key sheet {sheet.name} says it does not exist {side}"
                )
            detail = (
                f"{obs.key} does not exist {side} per key sheet {sheet.name}; "
                f"its {obs.year} cell ({obs.marker!r}) is excluded"
            )
            issues.append(RebaseIssue(IssueKind.NOT_APPLICABLE, obs.key, obs.year, detail))
        else:
            unmatched.append(obs)

    if unmatched and on_unmatched == "raise":
        listed = ", ".join(sorted({obs.key for obs in unmatched}))
        raise RebaseError(f"key(s) not on key sheet {sheet.name}: {listed}")
    if on_unmatched == "flag":
        issues += [
            RebaseIssue(IssueKind.UNMATCHED, obs.key, obs.year, f"{obs.key} is not on key sheet {sheet.name}")
            for obs in unmatched
        ]

    incomplete: list[str] = []
    for (target, year), contributions in parts.items():
        feeders = sheet.feeders(target, share)
        missing = sorted(feeders - {part.source for part in contributions})
        if missing:
            if on_incomplete == "raise":
                incomplete.append(f"{target} {year} is missing {', '.join(missing)}")
                continue
            if on_incomplete == "drop":
                continue
            for key in missing:
                detail = (
                    f"{key} {year} was not given but feeds {target} on sheet {sheet.name}; "
                    f"the re-based {target} {year} is null"
                )
                issues.append(RebaseIssue(IssueKind.MISSING_SOURCE, key, year, detail, target))
        only = contributions[0]
        if not missing and feeders == {target} and only.weight == 1.0:
            rows.append(RebasedRow(target, year, only.value, Flag.OBSERVED, (), only.marker))
            continue
        for part in contributions:
            if part.marker == NOT_AVAILABLE_MARKER:
                detail = f"{part.source} {year} is a '-' cell taken as 0 in the re-based {target} {year}"
                issues.append(RebaseIssue(IssueKind.ZERO_MARKER, part.source, year, detail, target))
        nulls = [part for part in contributions if part.value is None]
        for part in nulls:
            detail = f"{part.source} {year} is null ({part.marker!r}); the re-based {target} {year} is null"
            issues.append(RebaseIssue(IssueKind.NULL_INPUT, part.source, year, detail, target))
        complete = not nulls and not missing
        value = sum(part.weight * (part.value or 0.0) for part in contributions) if complete else None
        contributing = tuple(sorted({part.source for part in contributions}))
        rows.append(RebasedRow(target, year, value, Flag.REBASED, contributing))
    if incomplete:
        raise IncompleteError(
            f"feeding keys without an observation on key sheet {sheet.name}: {'; '.join(incomplete)}; "
            "add them or pass on_incomplete='flag'"
        )

    observed_years = [obs.year for obs in observations]
    breaks = tuple(b for b in CENSUS_BREAKS if min(observed_years) < b <= max(observed_years))
    edition = KeyEdition(source.name, source.url, source.sha256, from_year, to_year, share)
    rows.sort(key=lambda row: (row.year, row.key))
    return RebaseResult(tuple(rows), edition, tuple(issues), breaks)
