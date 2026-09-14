"""The consumer FeatureGroup a same-class ``GovDataFeature`` link needs: mloda executes such a join
only when a consumer needs a column from each side."""

from __future__ import annotations

from typing import Any, ClassVar

import pyarrow as pa
from mloda.provider import FeatureGroup, FeatureSet
from mloda.user import Feature, FeatureName, JoinSpec, Link, Options

from .destatis.reader import DestatisReader
from .govdata.bundeswahlleiterin import BundeswahlleiterinReader
from .govdata.feature import GovDataFeature

LAND_LOCATOR = {"name": "12411-0010", "startyear": 2024, "endyear": 2024}
KERG_URL = "https://www.bundeswahlleiterin.de/bundestagswahlen/2025/ergebnisse/opendata/btw25/csv/kerg.csv"
VOTERS = "Wahlberechtigte Erststimmen Endgültig"

LAND_LINK = Link.inner(
    JoinSpec(GovDataFeature, "1_variable_attribute_code"),
    JoinSpec(GovDataFeature, "Nr"),
    left_discriminator={DestatisReader.__name__: LAND_LOCATOR},
    right_discriminator={BundeswahlleiterinReader.__name__: KERG_URL},
)


class LandPopulationPerVoter(FeatureGroup):
    """Population per eligible voter by Land, joined on the DLAND / ``Nr`` Land codes."""

    NAME: ClassVar[str] = "land_population_per_voter"

    @classmethod
    def feature_names_supported(cls) -> set[str]:
        return {cls.NAME}

    def input_features(self, options: Options, feature_name: FeatureName) -> set[Feature] | None:
        return {
            Feature("value", options={DestatisReader.__name__: LAND_LOCATOR}, link=LAND_LINK),
            Feature(VOTERS, options={BundeswahlleiterinReader.__name__: KERG_URL}),
        }

    @classmethod
    def calculate_feature(cls, data: Any, features: FeatureSet) -> Any:
        pairs = zip(data.column("value").to_pylist(), data.column(VOTERS).to_pylist())
        ratio = pa.array([population / voters for population, voters in pairs], type=pa.float64())
        return data.append_column(cls.NAME, ratio)
