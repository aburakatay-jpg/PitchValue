"""Immutable configuration for leakage-safe ML dataset construction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MLDatasetValidationError(ValueError):
    """Raised when an ML dataset contract is structurally invalid."""


class FeatureProfile(StrEnum):
    FOOTBALL_PERFORMANCE_ONLY = "FOOTBALL_PERFORMANCE_ONLY"
    ODDS_INCLUSIVE_EXPERIMENT = "ODDS_INCLUSIVE_EXPERIMENT"


class MissingValuePolicy(StrEnum):
    PRESERVE_MISSING = "PRESERVE_MISSING"
    REJECT_ROW = "REJECT_ROW"


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise MLDatasetValidationError(f"{name} is required")


@dataclass(frozen=True)
class FeatureSchema:
    version: str = "v1"
    required_features: tuple[str, ...] = ()
    optional_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.version, "feature schema version")
        for name in self.required_features + self.optional_features:
            _identifier(name, "feature name")
        if len(set(self.required_features)) != len(self.required_features):
            raise MLDatasetValidationError("duplicate required feature")
        if len(set(self.optional_features)) != len(self.optional_features):
            raise MLDatasetValidationError("duplicate optional feature")
        if set(self.required_features) & set(self.optional_features):
            raise MLDatasetValidationError("feature cannot be both required and optional")

    @property
    def feature_order(self) -> tuple[str, ...]:
        return self.required_features + self.optional_features

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "required_features": list(self.required_features),
            "optional_features": list(self.optional_features),
        }


@dataclass(frozen=True)
class DatasetBuilderConfig:
    dataset_version: str = "v1"
    feature_schema: FeatureSchema = FeatureSchema()
    feature_profile: FeatureProfile = FeatureProfile.FOOTBALL_PERFORMANCE_ONLY
    missing_value_policy: MissingValuePolicy = MissingValuePolicy.PRESERVE_MISSING

    def __post_init__(self) -> None:
        _identifier(self.dataset_version, "dataset_version")
        if not isinstance(self.feature_schema, FeatureSchema):
            raise MLDatasetValidationError("feature_schema must use FeatureSchema")
        if not isinstance(self.feature_profile, FeatureProfile):
            raise MLDatasetValidationError("feature_profile must use FeatureProfile")
        if not isinstance(self.missing_value_policy, MissingValuePolicy):
            raise MLDatasetValidationError("missing_value_policy must use MissingValuePolicy")

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "feature_schema": self.feature_schema.to_dict(),
            "feature_profile": self.feature_profile.value,
            "missing_value_policy": self.missing_value_policy.value,
        }
