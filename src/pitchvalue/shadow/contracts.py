"""Immutable shadow evidence record without provider timestamp assumptions."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

SHADOW_CONTRACT_VERSION = "shadow_validation_contract_v1"


class ShadowSettlementStatus(StrEnum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    VOID = "VOID"


def _aware_optional(value: datetime | None, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{name} must be timezone-aware")


def _probability_optional(value: Decimal | None, name: str) -> None:
    if value is not None and (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < Decimal(0)
        or value > Decimal(1)
    ):
        raise ValueError(f"{name} must be a Decimal probability")


@dataclass(frozen=True)
class ShadowValidationRecord:
    run_id: str
    match_id: int
    prediction_as_of: datetime
    generated_at: datetime
    model_version: str
    feature_profile: str
    market_family: str
    selection: str
    model_probability: Decimal
    bookmaker: str | None
    decimal_odds: Decimal | None
    market_observed_at: datetime | None
    no_vig_market_probability: Decimal | None
    edge: Decimal | None
    dq_evidence_reference: str | None
    dq_status: str
    market_stability_reference: str | None
    market_stability_status: str
    calibration_confidence_reference: str | None
    calibration_confidence_status: str
    agreement: Decimal | None
    policy_decision: str
    publication_eligible: bool
    public_disabled_reason: str | None
    closing_reference: Decimal | None
    result: str | None
    settlement_status: ShadowSettlementStatus | None
    contract_version: str = SHADOW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "model_version",
            "feature_profile",
            "market_family",
            "selection",
            "dq_status",
            "market_stability_status",
            "calibration_confidence_status",
            "policy_decision",
            "contract_version",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be nonblank")
        if self.match_id <= 0:
            raise ValueError("match_id must be positive")
        _aware_optional(self.prediction_as_of, "prediction_as_of")
        _aware_optional(self.generated_at, "generated_at")
        _aware_optional(self.market_observed_at, "market_observed_at")
        _probability_optional(self.model_probability, "model_probability")
        _probability_optional(self.no_vig_market_probability, "no_vig_market_probability")
        if self.decimal_odds is not None and (
            not self.decimal_odds.is_finite() or self.decimal_odds <= Decimal(1)
        ):
            raise ValueError("decimal_odds must be greater than one")
        if self.edge is not None and (
            not self.edge.is_finite() or not Decimal(-1) <= self.edge <= Decimal(1)
        ):
            raise ValueError("edge must be a Decimal probability-point difference")
        _probability_optional(self.agreement, "agreement")
        if self.closing_reference is not None and (
            not self.closing_reference.is_finite() or self.closing_reference <= Decimal(1)
        ):
            raise ValueError("closing_reference must be decimal odds greater than one")
        if self.publication_eligible:
            raise ValueError("shadow validation records cannot be publication eligible")
        if self.public_disabled_reason is None or not self.public_disabled_reason.strip():
            raise ValueError("shadow record requires public-disabled reason")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, Decimal):
                result[field.name] = str(value)
            elif isinstance(value, datetime):
                result[field.name] = value.isoformat()
            elif isinstance(value, StrEnum):
                result[field.name] = value.value
            else:
                result[field.name] = value
        return result
