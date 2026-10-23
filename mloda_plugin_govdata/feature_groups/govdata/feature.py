"""Abstract root of the GovData source groups."""

from __future__ import annotations

from mloda.provider import SourceFeatureGroup


class GovDataFeature(SourceFeatureGroup):
    """Common base of every reader, so a ``feature_group="GovDataFeature"`` scope reaches them all."""
