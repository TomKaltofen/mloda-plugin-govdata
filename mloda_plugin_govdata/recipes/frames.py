"""Indexing the frames `mloda.run_all` returns for a two-frame recipe, by the columns each one carries."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class _FramesByColumn(dict[str, Any]):
    """A dict of column name to frame; a column two frames share raises on lookup, not at build time."""

    def __init__(self, frames: dict[str, Any], ambiguous: frozenset[str]) -> None:
        super().__init__(frames)
        self._ambiguous = ambiguous

    def __getitem__(self, column: str) -> Any:
        if column in self._ambiguous:
            raise ValueError(f"column {column!r} is in two frames; pick the frame by another column")
        return super().__getitem__(column)


def frames_by_column(result: Iterable[Any]) -> dict[str, Any]:
    """One frame per feature group and locator from a `mloda.run_all` result, indexed by column name.

    mloda frames carry no feature-set identity, so a two-frame recipe (mloda does not honor
    discriminators on a same-class link yet) is told apart by column name instead. A column shared
    by two frames raises only when that column itself is looked up, not for every other column.
    """
    frames: dict[str, Any] = {}
    ambiguous: set[str] = set()
    for table in result:
        for name in table.schema.names:
            if name in ambiguous:
                continue
            if name in frames:
                ambiguous.add(name)
                del frames[name]
            else:
                frames[name] = table
    return _FramesByColumn(frames, frozenset(ambiguous))
