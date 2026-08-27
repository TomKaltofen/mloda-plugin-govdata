"""Edition identity for the WP-D reference data (ADR 0006).

An ``Edition`` names which Gebietsstand and NUTS revision a ``map_ags_to_nuts()``
call resolves keys against, and carries the loaded crosswalk itself: the reference-
data identity it was built from (source, URL, sha256, covered year range).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mloda_plugin_govdata.feature_groups.govdata.core.cache import DEFAULT_CACHE_DIR, CacheMissError, DownloadCache

from .reference.eurostat import LauNutsRow, load_lau_nuts_de
from .reference.gv_isys import GvIsysChange
from .reference.sources import EUROSTAT_LAU_NUTS

# The pinned crosswalk is a single-year snapshot; this is the NUTS edition it represents,
# not to be confused with the differently-labelled Eurostat "Correspondence table" edition
# (see reference/eurostat.py:NutsCorrespondenceOverview and ADR 0006, Edition identity).
NUTS_VERSION = "2024"


@dataclass(frozen=True)
class Edition:
    gebietsstand: str
    nuts_version: str
    source: str
    url: str
    sha256: str | None
    year_range: tuple[int, int]
    lau_rows: tuple[LauNutsRow, ...]
    gv_isys_changes: tuple[GvIsysChange, ...] = ()


def load_edition(
    cache: DownloadCache, *, gv_isys_changes: Sequence[GvIsysChange] = (), revalidate: bool = False
) -> Edition:
    """Builds the current :class:`Edition` from the pinned Eurostat LAU-to-NUTS crosswalk.

    ``gv_isys_changes`` is optional history (e.g. from :func:`reference.gv_isys.load_gv_isys_changes`)
    used to redirect a since-retired Kreis code to its successor; without it, only Kreis codes
    already present in this edition's crosswalk resolve.
    """
    rows = load_lau_nuts_de(cache, revalidate=revalidate)
    if not rows:
        raise ValueError("Eurostat LAU-to-NUTS table loaded with zero rows; cannot build an edition")
    periods = {row.period for row in rows}
    if len(periods) > 1:
        raise ValueError(f"Eurostat LAU-to-NUTS rows span multiple PERIOD values: {sorted(periods)}")
    year = periods.pop()
    years = [year, *(c.effective_date_legal.year for c in gv_isys_changes)]
    return Edition(
        gebietsstand=str(year),
        nuts_version=NUTS_VERSION,
        source=EUROSTAT_LAU_NUTS.name,
        url=EUROSTAT_LAU_NUTS.url,
        sha256=EUROSTAT_LAU_NUTS.sha256,
        year_range=(min(years), max(years)),
        lau_rows=tuple(rows),
        gv_isys_changes=tuple(gv_isys_changes),
    )


def default_edition(cache_dir: str | os.PathLike[str] = DEFAULT_CACHE_DIR) -> Edition:
    """Loads the :class:`Edition` from whatever is already cached offline.

    ADR 0006: the default edition must raise with the fetch instruction on an empty
    cache rather than silently fall back to a bundled subset (there is no bundled subset).
    """
    with DownloadCache(Path(cache_dir)) as cache:
        try:
            return load_edition(cache, revalidate=False)
        except CacheMissError as exc:
            raise CacheMissError(
                f"{exc} Call load_edition(cache, revalidate=True) once to fetch and cache it."
            ) from exc
