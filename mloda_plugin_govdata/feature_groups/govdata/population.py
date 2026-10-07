"""Stuttgart population dataset (population theme, via GovData)."""

from __future__ import annotations

from typing import ClassVar

from .core.discovery import CC_BY_4_0
from .core.parse import ColumnType
from .reader import GovDataReader

POPULATION_SLUG = "einwohner-nach-altersgruppen-und-stadtbezirken"
POPULATION_SCHEMA: dict[str, ColumnType] = {
    "Stichtag": ColumnType.DATE,
    "Stadtbezirk": ColumnType.STRING,
    "Alter in 10 Gruppen": ColumnType.STRING,
    "Einwohner": ColumnType.INTEGER,
}


class StuttgartPopulationReader(GovDataReader):
    """Residents by age group and city district, with typed columns."""

    schema: ClassVar[dict[str, ColumnType] | None] = POPULATION_SCHEMA
    LICENSE: ClassVar[str | None] = CC_BY_4_0
