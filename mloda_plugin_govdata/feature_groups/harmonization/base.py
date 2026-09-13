"""Shared base for the harmonization FeatureGroups: chained derived groups over reader columns, PyArrow only."""

from __future__ import annotations

import re
from typing import ClassVar

from mloda.provider import COLUMN_SEPARATOR, ComputeFramework, FeatureChainParserMixin, FeatureGroup, FeatureSet
from mloda.user import Feature, FeatureName, Options
from mloda.user.pyarrow import PyArrowTable

from ..destatis.core.auth import OPTION_GENESIS_CREDENTIALS
from ..govdata.core.cache import DEFAULT_CACHE_DIR

# A part selector is lowercase letters and digits only, so ``~key__nuts2024`` never reads as one part.
PART_PATTERN = r"[a-z0-9]+"
_TRAILING_PART = re.compile(rf"{re.escape(COLUMN_SEPARATOR)}{PART_PATTERN}$")


class HarmonizationFeature(FeatureChainParserMixin, FeatureGroup):
    """Chained derived FeatureGroup over reader columns; the base matches nothing by itself.

    Children are explicit ``Feature`` objects: the consumer's reader locator forwards to them by
    default, this group's own option keys are carved out, and the GENESIS credentials are pulled
    from context, so a chained request resolves without the caller touching the reader features.
    """

    cache_dir: ClassVar[str] = str(DEFAULT_CACHE_DIR)  # reference tables are read offline from here
    # Context keys the children pull from the consumer; context never enters the feature hash.
    inherited_context_keys: ClassVar[frozenset[str]] = frozenset({OPTION_GENESIS_CREDENTIALS})

    @classmethod
    def compute_framework_rule(cls) -> set[type[ComputeFramework]] | None:
        return {PyArrowTable}

    @classmethod
    def child(cls, name: str) -> Feature:
        return Feature(
            name,
            forward_group_exclude=cls.declared_option_keys(),
            inherit_context_keys=cls.inherited_context_keys,
        )

    def single_source_child(self, options: Options, feature_name: FeatureName) -> set[Feature] | None:
        """The one parsed source column, re-wrapped as this group's own child.

        Shared by the groups whose ``input_features`` does nothing beyond that re-wrap; a group
        with more to add (extra sibling children, for example) still parses its own way.
        """
        parsed = FeatureChainParserMixin.input_features(self, options, feature_name) or set()
        return {self.child(str(source.name)) for source in parsed}

    @classmethod
    def source_column(cls, feature: Feature) -> str:
        """The one input column, from the chained name (``x__op``) or from ``in_features``."""
        (source,) = cls._extract_source_features(feature)
        return str(source)

    @staticmethod
    def base_name(feature_name: str) -> str:
        """``x__op~part`` requested alone still computes the whole ``x__op`` output; an upstream part stays."""
        return _TRAILING_PART.sub("", feature_name)

    @classmethod
    def by_base(cls, features: FeatureSet) -> dict[str, Feature]:
        """One feature per output base, computed once. Iterates in feature-name order (not base-name
        order), so a base/part collision deterministically keeps the part (its full name, with the
        trailing ``~part``, always sorts after the bare base name); the winner's Options are used,
        the loser's are dropped.
        """
        return {cls.base_name(str(feature.name)): feature for feature in features.get_sorted_features()}

    @classmethod
    def declared(cls, feature: Feature, key: str) -> str:
        """The operation from the name, checked against an explicit option that would otherwise be ignored.

        Reads the name-parsed value positionally (mloda's legacy path), not by ``key``: correct as
        long as a subclass's ``PREFIX_PATTERN`` has exactly one capture group, as all current ones do.
        """
        operation = cls._resolve_operation(feature, key)
        if operation is None:
            raise ValueError(f"{feature.name}: {key} is neither in the name nor in the options")
        explicit = feature.options.get(key)
        if explicit is not None and str(explicit) != operation:
            raise ValueError(f"{feature.name} names {key} {operation!r} but its option says {explicit!r}")
        return operation
