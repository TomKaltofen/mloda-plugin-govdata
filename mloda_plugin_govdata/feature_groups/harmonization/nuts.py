"""AGS-to-NUTS FeatureGroup: ``<key>__nuts2024`` over any AGS key column."""

from __future__ import annotations

from typing import Any, ClassVar, Literal, cast

import pyarrow as pa
from mloda.provider import DefaultOptionKeys, FeatureSet, property_spec
from mloda.user import Feature, FeatureName, Options

from ...harmonization.edition import NUTS_VERSION, Edition, default_edition
from ...harmonization.nuts import map_ags_to_nuts
from .base import HarmonizationFeature

PARTS: tuple[str, ...] = ("key", "nuts1", "nuts2", "nuts3", "version", "unmatched")
_POLICIES = {"raise": "fail loud", "flag": "null codes, the reason in ~unmatched"}


class AgsToNutsFeature(HarmonizationFeature):
    """``<key>__nuts2024``: NUTS codes for AGS keys from the pinned crosswalk edition.

    Appends, row-aligned, ``~key`` (the input key), ``~nuts1``, ``~nuts2``, ``~nuts3``, ``~version``
    (null when unmatched) and ``~unmatched`` (the reason, empty when matched). The edition in the name
    (or ``nuts_version``) must be the one the cache holds, so a result names what it was mapped with.
    """

    PREFIX_PATTERN = rf".*__nuts({NUTS_VERSION})(?:~\w+)?$"
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

    @classmethod
    def edition(cls) -> Edition:
        """The crosswalk edition from the offline cache; raises with the fetch instruction on a miss."""
        return default_edition(cls.cache_dir)

    def input_features(self, options: Options, feature_name: FeatureName) -> set[Feature] | None:
        parsed = super().input_features(options, feature_name) or set()
        return {self.child(str(source.name)) for source in parsed}

    @classmethod
    def calculate_feature(cls, data: Any, features: FeatureSet) -> Any:
        table: pa.Table = data
        edition = cls.edition()
        for feature in features.features:
            version = cls._resolve_operation(feature, "nuts_version")
            if version != edition.nuts_version:
                raise ValueError(
                    f"{feature.name} asks for NUTS {version}, the cached edition is NUTS {edition.nuts_version}"
                )
            name = cls.base_name(str(feature.name))
            raw = table.column(cls.source_column(feature)).to_pylist()
            keys = ["" if key is None else str(key) for key in raw]
            policy = _policy(feature.options)
            result = map_ags_to_nuts(keys, edition=edition, on_unmatched=policy)
            matched = {m.key: m for m in result.matched}
            reasons = {u.key: u.reason for u in result.unmatched}
            parts = {
                "key": raw,
                "nuts1": [matched[k].nuts1 if k in matched else None for k in keys],
                "nuts2": [matched[k].nuts2 if k in matched else None for k in keys],
                "nuts3": [matched[k].nuts3 if k in matched else None for k in keys],
                "version": [edition.nuts_version if k in matched else None for k in keys],
                "unmatched": [reasons.get(k, "") for k in keys],
            }
            for part in PARTS:
                table = table.append_column(f"{name}~{part}", pa.array(parts[part], pa.string()))
        return table


def _policy(options: Options) -> Literal["raise", "flag"]:
    value = options.get("nuts_on_unmatched") or "raise"
    if value not in ("raise", "flag"):
        raise ValueError(f"nuts_on_unmatched must be 'raise' or 'flag', got {value!r}")
    return cast(Literal["raise", "flag"], value)
