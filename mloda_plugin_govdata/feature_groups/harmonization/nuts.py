"""AGS-to-NUTS FeatureGroup: ``<key>__nuts2024`` over any AGS key column."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal, cast

import pyarrow as pa
from mloda.provider import DefaultOptionKeys, FeatureSet, property_spec
from mloda.user import Feature, FeatureName, Options

from ...harmonization.edition import NUTS_VERSION, Edition, load_edition
from ...harmonization.nuts import map_ags_to_nuts
from ...harmonization.reference.gv_isys import load_gv_isys_changes
from ..govdata.core.cache import CacheMissError, DownloadCache
from .base import PART_PATTERN, HarmonizationFeature

PARTS: tuple[str, ...] = ("key", "nuts1", "nuts2", "nuts3", "version", "unmatched")
NULL_KEY = "null key cell"
_POLICIES = {"raise": "fail loud", "flag": "null codes, the reason in ~unmatched"}


class AgsToNutsFeature(HarmonizationFeature):
    """``<key>__nuts2024``: NUTS codes for AGS keys from the pinned crosswalk edition.

    Appends, row-aligned, ``~key`` (the input key), ``~nuts1``, ``~nuts2``, ``~nuts3``, ``~version``
    (null when unmatched) and ``~unmatched`` (the reason, empty when matched). The edition in the name
    (or ``nuts_version``) must be the one the cache holds, so a result names what it was mapped with.
    """

    PREFIX_PATTERN = rf".*__nuts({NUTS_VERSION})(?:~{PART_PATTERN})?$"
    MIN_IN_FEATURES = 1
    MAX_IN_FEATURES = 1
    PROPERTY_MAPPING: ClassVar = {
        "nuts_version": property_spec(
            "NUTS edition the keys resolve against",
            strict=True,
            allowed_values={NUTS_VERSION: "the pinned Eurostat LAU-to-NUTS crosswalk"},
            context=False,
        ),
        "nuts_on_unmatched": property_spec(
            "Keys the edition cannot map", strict=True, allowed_values=_POLICIES, default="raise", context=False
        ),
        DefaultOptionKeys.in_features: property_spec("The AGS key column"),
    }
    # GV-ISys change files that redirect a retired Kreis key to its successor; the pinned years.
    history_years: ClassVar[tuple[int, ...]] = (2016,)

    @classmethod
    def edition(cls) -> Edition:
        """The crosswalk edition plus the pinned history, from the offline cache; a miss names the fetch calls."""
        with DownloadCache(Path(cls.cache_dir)) as cache:
            try:
                changes = [change for year in cls.history_years for change in load_gv_isys_changes(year, cache)]
                return load_edition(cache, gv_isys_changes=changes)
            except CacheMissError as exc:
                raise CacheMissError(
                    f"{exc} Call load_edition(cache, revalidate=True) and load_gv_isys_changes(year, cache, "
                    f"revalidate=True) for each year in {cls.history_years} once to fetch and cache them."
                ) from exc

    def input_features(self, options: Options, feature_name: FeatureName) -> set[Feature] | None:
        parsed = super().input_features(options, feature_name) or set()
        return {self.child(str(source.name)) for source in parsed}

    @classmethod
    def calculate_feature(cls, data: Any, features: FeatureSet) -> Any:
        table: pa.Table = data
        edition = cls.edition()
        for name, feature in cls.by_base(features).items():
            version = cls.declared(feature, "nuts_version")
            if version != edition.nuts_version:
                raise ValueError(
                    f"{feature.name} asks for NUTS {version}, the cached edition is NUTS {edition.nuts_version}"
                )
            source = cls.source_column(feature)
            column = table.column(source)
            if not (pa.types.is_string(column.type) or pa.types.is_large_string(column.type)):
                raise TypeError(
                    f"{source} must be a string column of AGS keys (leading zeros matter), got {column.type}"
                )
            raw: list[str | None] = column.to_pylist()
            policy = _policy(feature.options)
            nulls = [row for row, key in enumerate(raw) if key is None]
            if nulls and policy == "raise":
                raise ValueError(f"{source}, row {nulls[0]}: {NULL_KEY}; nuts_on_unmatched='flag' keeps such rows")
            present = list(dict.fromkeys(key for key in raw if key is not None))
            result = map_ags_to_nuts(present, edition=edition, on_unmatched=policy)
            matched = {m.key: m for m in result.matched}
            reasons = {u.key: u.reason for u in result.unmatched}
            parts = {
                "key": raw,
                "nuts1": [matched[k].nuts1 if k in matched else None for k in raw],
                "nuts2": [matched[k].nuts2 if k in matched else None for k in raw],
                "nuts3": [matched[k].nuts3 if k in matched else None for k in raw],
                "version": [edition.nuts_version if k in matched else None for k in raw],
                "unmatched": [NULL_KEY if k is None else reasons.get(k, "") for k in raw],
            }
            for part in PARTS:
                table = table.append_column(f"{name}~{part}", pa.array(parts[part], pa.string()))
        return table


def _policy(options: Options) -> Literal["raise", "flag"]:
    value = options.get("nuts_on_unmatched")
    if value is None:
        return "raise"
    if value not in ("raise", "flag"):
        raise ValueError(f"nuts_on_unmatched must be 'raise' or 'flag', got {value!r}")
    return cast(Literal["raise", "flag"], value)
