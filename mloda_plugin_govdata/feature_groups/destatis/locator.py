"""Destatis locator: identifies one GENESIS ``data/tablefile`` selection."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any

from .core.api import DEFAULT_LANGUAGE
from .core.hosts import resolve_host

# Both pinned M2 shapes: GENESIS-Online "12411-0015" (5 digits, one 1-4 digit segment) and
# Regionalstatistik "13211-02-05-4" (5 digits, up to three further 1-4 digit segments).
_TABLE_CODE = re.compile(r"^\d{5}(-\d{1,4}){1,3}$")


def _as_tuple(value: object, field_name: str) -> tuple[str, ...] | None:
    """A selection field as a tuple of strings; a bare string is one element, not split."""
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    raise TypeError(
        f"DestatisLocator.{field_name} must be a str, a sequence of str, or None, got {type(value).__name__}"
    )


@dataclass(frozen=True)
class DestatisLocator:
    """One GENESIS table selection: table code plus the optional M2 locator fields.

    ``area``, ``compress``, ``transpose``, ``timeslices``, ``job``, and ``stand`` are not locator
    fields in M2 (see ``docs/destatis-options.md``): they are pinned wire values or never sent, not
    caller-configurable. ``format`` is always ``ffcsv`` and likewise not a field. Frozen so it hashes
    natively inside ``Options.group``, like ``GovDataLocator``.
    """

    name: str
    regionalvariable: str | None = None
    regionalkey: tuple[str, ...] | None = field(default=None)
    classifyingvariable1: str | None = None
    classifyingkey1: tuple[str, ...] | None = field(default=None)
    classifyingvariable2: str | None = None
    classifyingkey2: tuple[str, ...] | None = field(default=None)
    classifyingvariable3: str | None = None
    classifyingkey3: tuple[str, ...] | None = field(default=None)
    classifyingvariable4: str | None = None
    classifyingkey4: tuple[str, ...] | None = field(default=None)
    classifyingvariable5: str | None = None
    classifyingkey5: tuple[str, ...] | None = field(default=None)
    contents: tuple[str, ...] | None = field(default=None)
    startyear: int | None = None
    endyear: int | None = None
    quality: bool = False
    host: str = "genesis"
    language: str = DEFAULT_LANGUAGE

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not _TABLE_CODE.fullmatch(name):
            raise ValueError(f"DestatisLocator: {self.name!r} is not a recognized GENESIS table code")
        object.__setattr__(self, "name", name)
        for name_field in (
            "regionalkey",
            "classifyingkey1",
            "classifyingkey2",
            "classifyingkey3",
            "classifyingkey4",
            "classifyingkey5",
            "contents",
        ):
            object.__setattr__(self, name_field, _as_tuple(getattr(self, name_field), name_field))
        resolve_host(self.host)  # raises ValueError for an unknown host name
        if self.language != DEFAULT_LANGUAGE:
            raise ValueError(f"DestatisLocator: language must be {DEFAULT_LANGUAGE!r} in M2, got {self.language!r}")

    @classmethod
    def from_string(cls, value: str) -> DestatisLocator:
        """A bare table code, every other field at its default."""
        return cls(name=value)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DestatisLocator:
        """The JSON-native form (plain dict, lists instead of tuples) recipes pass through options."""
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"DestatisLocator.from_dict: unknown field(s) {unknown}; known: {sorted(known)}")
        return cls(**data)

    @classmethod
    def coerce(cls, value: object) -> DestatisLocator | None:
        """Normalize a reader option value into a locator, or ``None`` if unusable."""
        if isinstance(value, DestatisLocator):
            return value
        if isinstance(value, str) and value:
            return cls.from_string(value)
        if isinstance(value, Mapping):
            return cls.from_dict(value)
        return None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe round trip: tuples become lists so ``json.dumps`` needs no custom encoder."""
        raw = dataclasses.asdict(self)
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in raw.items()}

    def describe(self) -> str:
        """Label for messages: the table code, qualified by host when it is not the default."""
        return self.name if self.host == "genesis" else f"{self.name}@{self.host}"
