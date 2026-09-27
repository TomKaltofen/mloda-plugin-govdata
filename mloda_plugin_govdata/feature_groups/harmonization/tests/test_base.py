"""HarmonizationFeature.by_base: stable output order and collision resolution, independent of
set iteration/hash seed."""

from mloda.provider import FeatureSet
from mloda.user import Feature, Options

from mloda_plugin_govdata.feature_groups.harmonization.base import HarmonizationFeature


def test_by_base_orders_by_feature_name_not_set_iteration() -> None:
    # Five distinct bases, not two or three: an unfixed set-iteration order has only a 1-in-120
    # chance of coincidentally matching this expected order on a given run.
    names = ["zeta__nuts2024", "alpha__nuts2024~nuts1", "mu__nuts2024", "beta__nuts2024", "eta__nuts2024"]
    features = FeatureSet([Feature(name) for name in names])
    result = HarmonizationFeature.by_base(features)
    assert list(result) == [HarmonizationFeature.base_name(name) for name in sorted(names)]


def test_by_base_collision_keeps_the_part_over_the_plain_base() -> None:
    # A base and its own ~part variant collide on base name; the ~part's full name sorts after
    # the bare base name, so it wins deterministically and the plain request's Options are dropped.
    plain = Feature("key__nuts2024", Options({"nuts_on_unmatched": "raise"}))
    part = Feature("key__nuts2024~unmatched", Options({"nuts_on_unmatched": "flag"}))
    result = HarmonizationFeature.by_base(FeatureSet([plain, part]))
    assert result["key__nuts2024"] is part
