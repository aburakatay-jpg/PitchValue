"""Deterministic schema-ordered feature-vector construction."""

from __future__ import annotations

from pitchvalue.ml.config import FeatureSchema
from pitchvalue.ml.contracts import FeatureRecord


def order_features(
    features: tuple[FeatureRecord, ...], schema: FeatureSchema
) -> tuple[FeatureRecord, ...]:
    by_name = {feature.name: feature for feature in features}
    return tuple(by_name[name] for name in schema.feature_order if name in by_name)
