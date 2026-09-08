"""Immutable, centrally validated Elo configuration."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Any


class EloValidationError(ValueError):
    """Raised when Elo configuration or replay context is invalid."""


def _require_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise EloValidationError(f"{field_name} must be a finite Decimal")
    return value


@dataclass(frozen=True)
class EloConfig:
    """INITIAL ELO PARAMETERS — SUBJECT TO BACKTEST CALIBRATION."""

    initial_rating: Decimal = Decimal("1500")
    k_factor: Decimal = Decimal("20")
    rating_scale: Decimal = Decimal("400")
    home_advantage: Decimal = Decimal("100")
    season_regression_factor: Decimal = Decimal("0.75")
    goal_margin_enabled: bool = False
    goal_margin_step: Decimal = Decimal("0.25")
    goal_margin_maximum: Decimal = Decimal("1.50")

    def __post_init__(self) -> None:
        decimal_names = (
            "initial_rating",
            "k_factor",
            "rating_scale",
            "home_advantage",
            "season_regression_factor",
            "goal_margin_step",
            "goal_margin_maximum",
        )
        for field_name in decimal_names:
            _require_decimal(getattr(self, field_name), field_name)
        if self.initial_rating <= 0:
            raise EloValidationError("initial_rating must be positive")
        if self.k_factor <= 0:
            raise EloValidationError("k_factor must be positive")
        if self.rating_scale <= 0:
            raise EloValidationError("rating_scale must be positive")
        if self.home_advantage < 0:
            raise EloValidationError("home_advantage cannot be negative")
        if not Decimal(0) <= self.season_regression_factor <= Decimal(1):
            raise EloValidationError("season_regression_factor must be within 0 and 1")
        if not isinstance(self.goal_margin_enabled, bool):
            raise EloValidationError("goal_margin_enabled must be boolean")
        if self.goal_margin_step < 0:
            raise EloValidationError("goal_margin_step cannot be negative")
        if self.goal_margin_maximum < 1:
            raise EloValidationError("goal_margin_maximum must be at least 1")

    def as_dict(self) -> dict[str, Any]:
        return {
            field.name: (
                str(getattr(self, field.name))
                if isinstance(getattr(self, field.name), Decimal)
                else getattr(self, field.name)
            )
            for field in fields(self)
        }


DEFAULT_ELO_CONFIG = EloConfig()
