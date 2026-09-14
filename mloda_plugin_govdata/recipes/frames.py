"""Indexing the frames `mloda.run_all` returns for a two-frame recipe, by the columns each one carries."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any


class _FramesByColumn(Mapping[str, Any]):
    """Read-only map of column name to frame; a column two frames share raises ValueError on lookup.

    `in` and `.get()` raise the same way (neither silently reports a shared column as absent);
    iteration and `len()` simply never surface it, since it resolves to no single frame.
    """

    def __init__(self, frames: dict[str, Any], ambiguous: frozenset[str]) -> None:
        self._frames = frames
        self._ambiguous = ambiguous

    def __getitem__(self, column: str) -> Any:
        if column in self._ambiguous:
            raise ValueError(f"column {column!r} is in two frames; pick the frame by another column")
        return self._frames[column]

    def __iter__(self) -> Iterator[str]:
        return iter(self._frames)

    def __len__(self) -> int:
        return len(self._frames)


def frames_by_column(result: Iterable[Any]) -> Mapping[str, Any]:
    """Indexes a `mloda.run_all` result by column name; use `RunResult.frames()` when the options that split
    the request (not just a distinguishing column) are what tell the frames apart."""
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
