"""Immutable configuration for the baseline Poisson goal model."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum
from typing import Any


class PoissonValidationError(ValueError):
    """Raised when Poisson inputs or configuration are mathematically invalid."""


class PartialHistoryPolicy(StrEnum):
    ALLOW_PARTIAL = "ALLOW_PARTIAL"
    REQUIRE_COMPLETE = "REQUIRE_COMPLETE"


@dataclass(frozen=True)
class PoissonConfig:
    """INITIAL SCORE-MATRIX TRUNCATION — SUBJECT TO VALIDATION."""

    max_goals: int = 10
    partial_history_policy: PartialHistoryPolicy = PartialHistoryPolicy.ALLOW_PARTIAL
    probability_tolerance: Decimal = Decimal("1e-12")
    maximum_lambda: Decimal = Decimal("50")

    def __post_init__(self) -> None:
        if not isinstance(self.max_goals, int) or isinstance(self.max_goals, bool):
            raise PoissonValidationError("max_goals must be an integer")
        if self.max_goals < 2:
            raise PoissonValidationError("max_goals must be at least 2")
        if not isinstance(self.partial_history_policy, PartialHistoryPolicy):
            raise PoissonValidationError("partial_history_policy must use PartialHistoryPolicy")
        if (
            not isinstance(self.probability_tolerance, Decimal)
            or not self.probability_tolerance.is_finite()
            or not Decimal(0) < self.probability_tolerance < Decimal(1)
        ):
            raise PoissonValidationError("probability_tolerance must be between 0 and 1")
        if (
            not isinstance(self.maximum_lambda, Decimal)
            or not self.maximum_lambda.is_finite()
            or self.maximum_lambda <= 0
        ):
            raise PoissonValidationError("maximum_lambda must be a positive finite Decimal")

    def as_dict(self) -> dict[str, Any]:
        return {
            field.name: (
                getattr(self, field.name).value
                if isinstance(getattr(self, field.name), StrEnum)
                else str(getattr(self, field.name))
                if isinstance(getattr(self, field.name), Decimal)
                else getattr(self, field.name)
            )
            for field in fields(self)
        }


DEFAULT_POISSON_CONFIG = PoissonConfig()
