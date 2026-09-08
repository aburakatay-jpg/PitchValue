"""Pure, score-derived pre-match football feature computation."""

from pitchvalue.features.config import DEFAULT_FEATURE_CONFIG, FeatureConfig
from pitchvalue.features.contracts import HistoricalMatch, MatchFeatures, TargetFixture
from pitchvalue.features.engine import compute_match_features

__all__ = [
    "DEFAULT_FEATURE_CONFIG",
    "FeatureConfig",
    "HistoricalMatch",
    "MatchFeatures",
    "TargetFixture",
    "compute_match_features",
]
