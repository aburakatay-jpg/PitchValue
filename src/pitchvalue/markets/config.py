"""Immutable configuration for provider-agnostic market mathematics."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum
from typing import Any


class MarketMathError(ValueError):
    """Raised when odds, group, or market-math configuration is invalid."""


class NoVigMethod(StrEnum):
    PROPORTIONAL = "PROPORTIONAL"
    SHIN = "SHIN"
    POWER = "POWER"
    ADDITIVE = "ADDITIVE"


@dataclass(frozen=True)
class MarketMathConfig:
    """Pure Decimal behavior and provisional market diagnostics."""

    no_vig_method: NoVigMethod = NoVigMethod.PROPORTIONAL
    decimal_precision: int = 50
    probability_sum_tolerance: Decimal = Decimal("1E-24")
    suspicious_overround_threshold: Decimal = Decimal("0.15")
    suspicious_underround_threshold: Decimal = Decimal("-0.02")

    def __post_init__(self) -> None:
        if not isinstance(self.no_vig_method, NoVigMethod):
            raise MarketMathError("no_vig_method must use NoVigMethod")
        if (
            not isinstance(self.decimal_precision, int)
            or isinstance(self.decimal_precision, bool)
            or self.decimal_precision < 28
        ):
            raise MarketMathError("decimal_precision must be an integer of at least 28")
        for field_name in (
            "probability_sum_tolerance",
            "suspicious_overround_threshold",
            "suspicious_underround_threshold",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise MarketMathError(f"{field_name} must be a finite Decimal")
        if not Decimal(0) < self.probability_sum_tolerance < Decimal(1):
            raise MarketMathError("probability_sum_tolerance must be within (0, 1)")
        if self.suspicious_overround_threshold <= 0:
            raise MarketMathError("suspicious_overround_threshold must be positive")
        if self.suspicious_underround_threshold >= 0:
            raise MarketMathError("suspicious_underround_threshold must be negative")

    def as_dict(self) -> dict[str, Any]:
        return {
            field.name: (
                value.value
                if isinstance(value, StrEnum)
                else str(value)
                if isinstance(value, Decimal)
                else value
            )
            for field in fields(self)
            for value in (getattr(self, field.name),)
        }


DEFAULT_MARKET_MATH_CONFIG = MarketMathConfig()
