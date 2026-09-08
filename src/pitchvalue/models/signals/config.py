"""Immutable configuration for model-signal adaptation and agreement."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum
from typing import Any


class SignalValidationError(ValueError):
    """Raised when a signal or agreement contract is invalid."""


class TieBreakingPolicy(StrEnum):
    AMBIGUOUS = "AMBIGUOUS"


class ModelFamily(StrEnum):
    POISSON = "POISSON"
    ELO = "ELO"
    FORM = "FORM"
    ML = "ML"


CANONICAL_MODEL_FAMILY_ORDER = (
    ModelFamily.POISSON,
    ModelFamily.ELO,
    ModelFamily.FORM,
    ModelFamily.ML,
)


def _finite_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise SignalValidationError(f"{name} must be a finite Decimal")
    return value


@dataclass(frozen=True)
class SignalAgreementConfig:
    """Provisional adapter thresholds and planned four-family ensemble shape."""

    configured_model_families: tuple[ModelFamily, ...] = CANONICAL_MODEL_FAMILY_ORDER
    required_agreement_ratio: Decimal = Decimal("0.75")
    minimum_usable_models: int = 3
    elo_away_threshold: Decimal = Decimal("0.45")
    elo_home_threshold: Decimal = Decimal("0.55")
    form_away_threshold: Decimal = Decimal("-0.10")
    form_home_threshold: Decimal = Decimal("0.10")
    poisson_ambiguity_tolerance: Decimal = Decimal("0.0001")
    poisson_residual_mass_tolerance: Decimal = Decimal("0.001")
    tie_breaking_policy: TieBreakingPolicy = TieBreakingPolicy.AMBIGUOUS

    def __post_init__(self) -> None:
        families = self.configured_model_families
        if not isinstance(families, tuple) or not families:
            raise SignalValidationError("configured_model_families must be a non-empty tuple")
        if any(not isinstance(family, ModelFamily) for family in families):
            raise SignalValidationError("configured model families must use ModelFamily")
        if len(set(families)) != len(families):
            raise SignalValidationError("configured model families cannot contain duplicates")
        canonical_subset = tuple(
            family for family in CANONICAL_MODEL_FAMILY_ORDER if family in families
        )
        if families != canonical_subset:
            raise SignalValidationError("configured model families must use canonical order")
        ratio = _finite_decimal(self.required_agreement_ratio, "required_agreement_ratio")
        if not Decimal(0) < ratio <= Decimal(1):
            raise SignalValidationError("required_agreement_ratio must be within (0, 1]")
        if (
            not isinstance(self.minimum_usable_models, int)
            or isinstance(self.minimum_usable_models, bool)
            or not 1 <= self.minimum_usable_models <= len(families)
        ):
            raise SignalValidationError(
                "minimum_usable_models must be within configured model count"
            )
        elo_away = _finite_decimal(self.elo_away_threshold, "elo_away_threshold")
        elo_home = _finite_decimal(self.elo_home_threshold, "elo_home_threshold")
        if not Decimal(0) <= elo_away < Decimal("0.5") < elo_home <= Decimal(1):
            raise SignalValidationError("Elo thresholds must bound 0.5")
        if elo_away != Decimal(1) - elo_home:
            raise SignalValidationError("Elo thresholds must be symmetric around 0.5")
        form_away = _finite_decimal(self.form_away_threshold, "form_away_threshold")
        form_home = _finite_decimal(self.form_home_threshold, "form_home_threshold")
        if not Decimal(-1) <= form_away < 0 < form_home <= Decimal(1):
            raise SignalValidationError("Form thresholds must bound zero")
        if form_away != -form_home:
            raise SignalValidationError("Form thresholds must be symmetric around zero")
        ambiguity = _finite_decimal(self.poisson_ambiguity_tolerance, "poisson_ambiguity_tolerance")
        residual = _finite_decimal(
            self.poisson_residual_mass_tolerance,
            "poisson_residual_mass_tolerance",
        )
        if not Decimal(0) <= ambiguity < Decimal(1):
            raise SignalValidationError("Poisson ambiguity tolerance must be within [0, 1)")
        if not Decimal(0) <= residual <= Decimal(1):
            raise SignalValidationError("Poisson residual tolerance must be within [0, 1]")
        if not isinstance(self.tie_breaking_policy, TieBreakingPolicy):
            raise SignalValidationError("tie_breaking_policy must use TieBreakingPolicy")

    def as_dict(self) -> dict[str, Any]:
        return {
            field.name: (
                [item.value for item in value]
                if isinstance(value, tuple)
                else value.value
                if isinstance(value, StrEnum)
                else str(value)
                if isinstance(value, Decimal)
                else value
            )
            for field in fields(self)
            for value in (getattr(self, field.name),)
        }


DEFAULT_SIGNAL_AGREEMENT_CONFIG = SignalAgreementConfig()
