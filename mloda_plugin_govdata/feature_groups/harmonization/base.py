"""Shared base for the harmonization FeatureGroups: chained derived groups over reader columns, PyArrow only."""

from __future__ import annotations

from typing import ClassVar

from mloda.provider import COLUMN_SEPARATOR, ComputeFramework, FeatureChainParserMixin, FeatureGroup
from mloda.user import Feature, PyArrowTable

from ..destatis.core.auth import OPTION_GENESIS_CREDENTIALS
from ..govdata.core.cache import DEFAULT_CACHE_DIR


class HarmonizationFeature(FeatureChainParserMixin, FeatureGroup):
    """Chained derived FeatureGroup over reader columns; the base matches nothing by itself.

    Children are explicit ``Feature`` objects: the consumer's reader locator forwards to them by
    default, this group's own option keys are carved out, and the GENESIS credentials are pulled
    from context, so a chained request resolves without the caller touching the reader features.
    """

    cache_dir: ClassVar[str] = str(DEFAULT_CACHE_DIR)  # reference tables are read offline from here

    @classmethod
    def compute_framework_rule(cls) -> set[type[ComputeFramework]] | None:
        return {PyArrowTable}

    @classmethod
    def child(cls, name: str) -> Feature:
        return Feature(
            name,
            forward_group_exclude=cls.declared_option_keys(),
            inherit_context_keys={OPTION_GENESIS_CREDENTIALS},
        )

    @classmethod
    def source_column(cls, feature: Feature) -> str:
        """The one input column, from the chained name (``x__op``) or from ``in_features``."""
        (source,) = cls._extract_source_features(feature)
        return str(source)

    @staticmethod
    def base_name(feature_name: str) -> str:
        """``x__op~part`` requested alone still computes the whole ``x__op`` output."""
        return feature_name.split(COLUMN_SEPARATOR, 1)[0]
