"""Immutable configuration for the transparent form/performance signal."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum
from typing import Any


class FormValidationError(ValueError):
    """Raised when form configuration or input violates a model contract."""


class PartialCoveragePolicy(StrEnum):
    USE_PARTIAL = "USE_PARTIAL"
    EXCLUDE_PARTIAL = "EXCLUDE_PARTIAL"


class MissingComponentPolicy(StrEnum):
    EXCLUDE = "EXCLUDE"
    NEUTRAL_IMPUTE = "NEUTRAL_IMPUTE"


def _decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise FormValidationError(f"{field_name} must be a finite Decimal")
    return value


@dataclass(frozen=True)
class ComponentWeights:
    recent_form: Decimal = Decimal("0.25")
    extended_form: Decimal = Decimal("0.15")
    venue_form: Decimal = Decimal("0.25")
    attack: Decimal = Decimal("0.15")
    defense: Decimal = Decimal("0.15")
    schedule: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        values = tuple(_decimal(getattr(self, field.name), field.name) for field in fields(self))
        if any(value < 0 or value > 1 for value in values):
            raise FormValidationError("component weights must be between 0 and 1")
        if sum(values, Decimal(0)) != Decimal(1):
            raise FormValidationError("component weights must total 1")


@dataclass(frozen=True)
class InnerWeights:
    primary: Decimal
    secondary: Decimal

    def __post_init__(self) -> None:
        primary = _decimal(self.primary, "primary")
        secondary = _decimal(self.secondary, "secondary")
        if primary < 0 or secondary < 0 or primary + secondary != 1:
            raise FormValidationError("inner weights must be non-negative and total 1")


@dataclass(frozen=True)
class FormModelConfig:
    """INITIAL FORM SIGNAL WEIGHTS — SUBJECT TO BACKTEST CALIBRATION."""

    component_weights: ComponentWeights = ComponentWeights()
    form_inner_weights: InnerWeights = InnerWeights(Decimal("0.70"), Decimal("0.30"))
    performance_inner_weights: InnerWeights = InnerWeights(Decimal("0.40"), Decimal("0.60"))
    goal_difference_minimum: Decimal = Decimal("-2")
    goal_difference_maximum: Decimal = Decimal("2")
    attack_ratio_maximum: Decimal = Decimal("2")
    defense_ratio_maximum: Decimal = Decimal("2")
    neutral_score: Decimal = Decimal("50")
    short_rest_days: Decimal = Decimal("4")
    adequate_rest_days: Decimal = Decimal("7")
    short_rest_penalty: Decimal = Decimal("15")
    adequate_rest_bonus: Decimal = Decimal("5")
    congestion_7_day_threshold: int = 2
    congestion_14_day_threshold: int = 4
    congestion_7_day_penalty: Decimal = Decimal("5")
    congestion_14_day_penalty: Decimal = Decimal("3")
    schedule_score_minimum: Decimal = Decimal("20")
    schedule_score_maximum: Decimal = Decimal("60")
    partial_coverage_policy: PartialCoveragePolicy = PartialCoveragePolicy.USE_PARTIAL
    missing_component_policy: MissingComponentPolicy = MissingComponentPolicy.EXCLUDE
    minimum_scored_components: int = 4
    require_overall_form: bool = True
    require_venue_form: bool = True
    require_attack_or_defense: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.component_weights, ComponentWeights):
            raise FormValidationError("component_weights must use ComponentWeights")
        if not isinstance(self.form_inner_weights, InnerWeights) or not isinstance(
            self.performance_inner_weights, InnerWeights
        ):
            raise FormValidationError("inner weights must use InnerWeights")
        decimal_names = (
            "goal_difference_minimum",
            "goal_difference_maximum",
            "attack_ratio_maximum",
            "defense_ratio_maximum",
            "neutral_score",
            "short_rest_days",
            "adequate_rest_days",
            "short_rest_penalty",
            "adequate_rest_bonus",
            "congestion_7_day_penalty",
            "congestion_14_day_penalty",
            "schedule_score_minimum",
            "schedule_score_maximum",
        )
        for field_name in decimal_names:
            _decimal(getattr(self, field_name), field_name)
        if not self.goal_difference_minimum < 0 < self.goal_difference_maximum:
            raise FormValidationError("goal-difference bounds must surround zero")
        if self.attack_ratio_maximum <= 1 or self.defense_ratio_maximum <= 1:
            raise FormValidationError("attack and defense ratio maxima must exceed 1")
        if not Decimal(0) <= self.neutral_score <= Decimal(100):
            raise FormValidationError("neutral_score must be within 0 and 100")
        if not Decimal(0) <= self.short_rest_days < self.adequate_rest_days:
            raise FormValidationError("rest thresholds must be non-negative and ordered")
        if self.short_rest_penalty < 0 or self.adequate_rest_bonus < 0:
            raise FormValidationError("rest adjustments cannot be negative")
        for field_name in ("congestion_7_day_threshold", "congestion_14_day_threshold"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise FormValidationError("congestion thresholds must be non-negative integers")
        if self.congestion_7_day_penalty < 0 or self.congestion_14_day_penalty < 0:
            raise FormValidationError("congestion penalties cannot be negative")
        if not (
            Decimal(0)
            <= self.schedule_score_minimum
            <= self.neutral_score
            <= self.schedule_score_maximum
            <= Decimal(100)
        ):
            raise FormValidationError("schedule score bounds must contain neutral_score")
        if not isinstance(self.partial_coverage_policy, PartialCoveragePolicy):
            raise FormValidationError("invalid partial coverage policy")
        if not isinstance(self.missing_component_policy, MissingComponentPolicy):
            raise FormValidationError("invalid missing component policy")
        if (
            not isinstance(self.minimum_scored_components, int)
            or isinstance(self.minimum_scored_components, bool)
            or not 1 <= self.minimum_scored_components <= 6
        ):
            raise FormValidationError("minimum_scored_components must be within 1 and 6")
        for field_name in (
            "require_overall_form",
            "require_venue_form",
            "require_attack_or_defense",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise FormValidationError(f"{field_name} must be boolean")

    def as_dict(self) -> dict[str, Any]:
        def serialize(value: object) -> object:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, StrEnum):
                return value.value
            if hasattr(value, "__dataclass_fields__"):
                return {
                    field.name: serialize(getattr(value, field.name))
                    for field in fields(value)  # type: ignore[arg-type]
                }
            return value

        return {field.name: serialize(getattr(self, field.name)) for field in fields(self)}


DEFAULT_FORM_CONFIG = FormModelConfig()
