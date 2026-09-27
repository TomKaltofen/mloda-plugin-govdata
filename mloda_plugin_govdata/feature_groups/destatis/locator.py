"""Destatis locator: identifies one GENESIS ``data/tablefile`` selection."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any

from .core.api import CLASSIFYING_KEYS, CLASSIFYING_VARIABLES, DEFAULT_LANGUAGE, PINNED_TABLEFILE_FIELDS
from .core.hosts import GENESIS_ONLINE, resolve_host

# Both known shapes: GENESIS-Online "12411-0015" (5 digits, one 1-4 digit segment) and
# Regionalstatistik "13211-02-05-4" (5 digits, up to three further 1-4 digit segments);
# docs/destatis-options.md documents the 15-char spec limit.
_TABLE_CODE = re.compile(r"^\d{5}(-\d{1,4}){1,3}$")
_MAX_NAME_LENGTH = 15
_YEAR_RANGE = range(1900, 2101)
# Selection fields by shape: one dimension code each, or a list of keys (measure codes for contents).
_CODE_FIELDS = ("regionalvariable", *CLASSIFYING_VARIABLES)
_LIST_FIELDS = ("regionalkey", *CLASSIFYING_KEYS, "contents")
# Locator fields that are not sent as themselves: host picks the URL, quality goes out as on/off.
_NOT_SENT_AS_IS = frozenset({"host", "quality"})


def _as_tuple(value: object, field_name: str) -> tuple[str, ...] | None:
    """A selection field as a tuple of stripped strings; blank elements and an empty result are ``None``.

    ``bytes``/``bytearray`` are rejected even though they are a ``Sequence``: iterating one yields
    integers, not the per-key strings a caller means. Every element must already be a ``str``: an
    int can't be zero-padded back (which AGS level, 2/5/8 digits, is not decidable from a bare int),
    so it is rejected rather than guessed, like every other non-str element.
    """
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        raise TypeError(f"DestatisLocator.{field_name} must be a str, a sequence of str, or None, not bytes")
    if isinstance(value, str):
        items: Sequence[object] = (value,)
    elif isinstance(value, Sequence):
        items = value
    else:
        raise TypeError(
            f"DestatisLocator.{field_name} must be a str, a sequence of str, or None, got {type(value).__name__}"
        )
    for item in items:
        if not isinstance(item, str):
            hint = (
                ": an int loses a key's leading zeros" if isinstance(item, int) and not isinstance(item, bool) else ""
            )
            raise TypeError(
                f"DestatisLocator.{field_name} element {item!r} must be a str{hint}, got {type(item).__name__}"
            )
    cleaned = tuple(str(item).strip() for item in items if str(item).strip())
    return cleaned or None


def _clean_scalar(value: str | None, field_name: str) -> str | None:
    """A scalar selection field, stripped; blank becomes ``None`` (the same "not sent" meaning)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"DestatisLocator.{field_name} must be a str or None, got {type(value).__name__}")
    return value.strip() or None


def _clean_year(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"DestatisLocator.{field_name} must be an int, got {type(value).__name__}")
    if value not in _YEAR_RANGE:
        raise ValueError(f"DestatisLocator.{field_name}: {value} is outside {_YEAR_RANGE.start}-{_YEAR_RANGE.stop - 1}")
    return value


@dataclass(frozen=True)
class DestatisLocator:
    """One GENESIS table selection: table code plus the optional locator fields.

    ``area``, ``compress``, ``transpose``, ``timeslices``, ``job``, and ``stand`` are not locator
    fields (see ``docs/destatis-options.md``): they are pinned wire values or never sent, not
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
    host: str = GENESIS_ONLINE.name
    language: str = DEFAULT_LANGUAGE

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError(f"DestatisLocator: name must be a str, got {type(self.name).__name__}")
        name = self.name.strip()
        if len(name) > _MAX_NAME_LENGTH or not _TABLE_CODE.fullmatch(name):
            raise ValueError(f"DestatisLocator: {self.name!r} is not a recognized GENESIS table code")
        object.__setattr__(self, "name", name)
        for scalar_field in _CODE_FIELDS:
            object.__setattr__(self, scalar_field, _clean_scalar(getattr(self, scalar_field), scalar_field))
        for tuple_field in _LIST_FIELDS:
            object.__setattr__(self, tuple_field, _as_tuple(getattr(self, tuple_field), tuple_field))
        object.__setattr__(self, "startyear", _clean_year(self.startyear, "startyear"))
        object.__setattr__(self, "endyear", _clean_year(self.endyear, "endyear"))
        if self.startyear is not None and self.endyear is not None and self.startyear > self.endyear:
            raise ValueError(f"DestatisLocator: startyear {self.startyear} is after endyear {self.endyear}")
        if not isinstance(self.quality, bool):
            raise TypeError(f"DestatisLocator: quality must be a bool, got {type(self.quality).__name__}")
        object.__setattr__(self, "host", resolve_host(self.host).name)
        # The ffcsv parser reads German decimal commas; an "en" reply would parse cleanly into wrong values.
        if self.language != DEFAULT_LANGUAGE:
            raise ValueError(f"DestatisLocator: language must be {DEFAULT_LANGUAGE!r}, got {self.language!r}")

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
        if "name" not in data:
            raise ValueError("DestatisLocator.from_dict: missing required field 'name'")
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

    def tablefile_fields(self) -> dict[str, object]:
        """``data/tablefile`` form fields: the locator fields that are not None, the pinned ones, quality as on/off.

        Pass it as ``fields`` to ``ParameterCache.get_or_fetch``, which sorts the key lists and stringifies the years.
        """
        values = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in _NOT_SENT_AS_IS}
        wire: dict[str, object] = {name: value for name, value in values.items() if value is not None}
        return {**wire, **PINNED_TABLEFILE_FIELDS, "quality": "on" if self.quality else "off"}

    def describe(self) -> str:
        """Label for messages: the table code, qualified by host when it is not the default."""
        return self.name if self.host == GENESIS_ONLINE.name else f"{self.name}@{self.host}"
