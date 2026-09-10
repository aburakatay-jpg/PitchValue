"""Immutable configuration for leakage-safe ML dataset construction."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
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


class PreprocessingPolicy(StrEnum):
    TRAIN_MEAN_STANDARDIZE_WITH_INDICATOR = "TRAIN_MEAN_STANDARDIZE_WITH_INDICATOR"


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


@dataclass(frozen=True)
class MLTrainingConfig:
    """Deterministic engineering defaults for the first probabilistic ML baseline."""

    model_version: str = "multinomial_logistic_v1"
    feature_profile: FeatureProfile = FeatureProfile.FOOTBALL_PERFORMANCE_ONLY
    preprocessing_policy: PreprocessingPolicy = (
        PreprocessingPolicy.TRAIN_MEAN_STANDARDIZE_WITH_INDICATOR
    )
    minimum_training_samples: int = 500
    minimum_class_samples: int = 1
    epochs: int = 60
    learning_rate: Decimal = Decimal("0.05")
    l2_strength: Decimal = Decimal("0.001")
    random_seed: int = 16

    def __post_init__(self) -> None:
        _identifier(self.model_version, "model_version")
        if self.feature_profile is not FeatureProfile.FOOTBALL_PERFORMANCE_ONLY:
            raise MLDatasetValidationError("TASK 16 baseline requires FOOTBALL_PERFORMANCE_ONLY")
        if not isinstance(self.preprocessing_policy, PreprocessingPolicy):
            raise MLDatasetValidationError("preprocessing_policy must use PreprocessingPolicy")
        for name in ("minimum_training_samples", "minimum_class_samples", "epochs"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise MLDatasetValidationError(f"{name} must be at least 1")
        for name in ("learning_rate", "l2_strength"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise MLDatasetValidationError(f"{name} must be a finite Decimal")
        if self.learning_rate <= 0:
            raise MLDatasetValidationError("learning_rate must be positive")
        if self.l2_strength < 0:
            raise MLDatasetValidationError("l2_strength cannot be negative")
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise MLDatasetValidationError("random_seed must be an integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "feature_profile": self.feature_profile.value,
            "preprocessing_policy": self.preprocessing_policy.value,
            "minimum_training_samples": self.minimum_training_samples,
            "minimum_class_samples": self.minimum_class_samples,
            "epochs": self.epochs,
            "learning_rate": str(self.learning_rate),
            "l2_strength": str(self.l2_strength),
            "random_seed": self.random_seed,
        }
