"""Typed, deterministic shared model-signal and agreement contracts."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.models.signals.config import ModelFamily, SignalValidationError
from pitchvalue.prediction.contracts import MarketFamily, Selection

_MARKET_SELECTIONS = {
    MarketFamily.MATCH_RESULT: frozenset({Selection.HOME, Selection.DRAW, Selection.AWAY}),
    MarketFamily.TOTAL_GOALS: frozenset({Selection.OVER, Selection.UNDER}),
    MarketFamily.BTTS: frozenset({Selection.YES, Selection.NO}),
    MarketFamily.DOUBLE_CHANCE: frozenset({Selection.ONE_X, Selection.X_TWO, Selection.ONE_TWO}),
    MarketFamily.HOME_TEAM_TOTAL: frozenset({Selection.OVER, Selection.UNDER}),
    MarketFamily.AWAY_TEAM_TOTAL: frozenset({Selection.OVER, Selection.UNDER}),
}
_MARKET_LINES = {
    MarketFamily.MATCH_RESULT: None,
    MarketFamily.TOTAL_GOALS: frozenset({Decimal("1.5"), Decimal("2.5")}),
    MarketFamily.BTTS: None,
    MarketFamily.DOUBLE_CHANCE: None,
    MarketFamily.HOME_TEAM_TOTAL: frozenset({Decimal("0.5"), Decimal("1.5")}),
    MarketFamily.AWAY_TEAM_TOTAL: frozenset({Decimal("0.5"), Decimal("1.5")}),
}


class SignalStatus(StrEnum):
    READY = "READY"
    INPUT_INSUFFICIENT = "INPUT_INSUFFICIENT"
    ANALYSIS_UNAVAILABLE = "ANALYSIS_UNAVAILABLE"
    INVALID = "INVALID"
    UNSUPPORTED_MARKET = "UNSUPPORTED_MARKET"
    AMBIGUOUS = "AMBIGUOUS"


class DirectionalPreference(StrEnum):
    HOME = "HOME"
    NEUTRAL = "NEUTRAL"
    AWAY = "AWAY"


@dataclass(frozen=True)
class SignalDiagnostic:
    name: str
    value: Decimal | int | str | bool | None


def _require_identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SignalValidationError(f"{name} is required")


def _probability(value: Decimal | None, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal) or not value.is_finite():
        raise SignalValidationError(f"{name} must be a finite Decimal")
    if not Decimal(0) <= value <= Decimal(1):
        raise SignalValidationError(f"{name} must be between 0 and 1")


def validate_market_position(
    market: MarketFamily,
    selection: Selection,
    line: Decimal | None,
) -> None:
    if selection not in _MARKET_SELECTIONS[market]:
        raise SignalValidationError("selection is not valid for market")
    allowed_lines = _MARKET_LINES[market]
    if allowed_lines is None and line is not None:
        raise SignalValidationError("line must be absent for market")
    if allowed_lines is not None and line not in allowed_lines:
        raise SignalValidationError("line is not valid for market")


@dataclass(frozen=True)
class ModelSignal:
    model_family: ModelFamily
    model_name: str
    match_id: str
    market: MarketFamily
    selection: Selection | None
    direction: DirectionalPreference | None
    signal_status: SignalStatus
    normalized_strength: Decimal | None
    line: Decimal | None = None
    probability: Decimal | None = None
    raw_value: Decimal | None = None
    diagnostics: tuple[SignalDiagnostic, ...] = ()
    correlation_group: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_family, ModelFamily):
            raise SignalValidationError("model_family must use ModelFamily")
        _require_identifier(self.model_name, "model_name")
        _require_identifier(self.match_id, "match_id")
        if not isinstance(self.market, MarketFamily):
            raise SignalValidationError("market must use MarketFamily")
        if self.selection is not None and not isinstance(self.selection, Selection):
            raise SignalValidationError("selection must use Selection")
        if self.line is not None and (
            not isinstance(self.line, Decimal) or not self.line.is_finite()
        ):
            raise SignalValidationError("line must be a finite Decimal")
        allowed_lines = _MARKET_LINES[self.market]
        if allowed_lines is None and self.line is not None:
            raise SignalValidationError("line must be absent for market")
        if self.direction is not None and not isinstance(self.direction, DirectionalPreference):
            raise SignalValidationError("direction must use DirectionalPreference")
        if not isinstance(self.signal_status, SignalStatus):
            raise SignalValidationError("signal_status must use SignalStatus")
        _probability(self.normalized_strength, "normalized_strength")
        _probability(self.probability, "probability")
        if self.raw_value is not None and (
            not isinstance(self.raw_value, Decimal) or not self.raw_value.is_finite()
        ):
            raise SignalValidationError("raw_value must be a finite Decimal")
        if self.signal_status is SignalStatus.READY:
            if self.normalized_strength is None:
                raise SignalValidationError("READY signal requires normalized_strength")
            if self.selection is None and self.direction is not DirectionalPreference.NEUTRAL:
                raise SignalValidationError(
                    "READY signal requires explicit selection or NEUTRAL direction"
                )
            if self.selection is not None:
                validate_market_position(self.market, self.selection, self.line)
        elif self.selection is not None:
            raise SignalValidationError("non-READY signal cannot support a selection")
        if self.direction is DirectionalPreference.HOME and self.selection is not Selection.HOME:
            raise SignalValidationError("HOME direction requires home selection")
        if self.direction is DirectionalPreference.AWAY and self.selection is not Selection.AWAY:
            raise SignalValidationError("AWAY direction requires away selection")
        if self.direction is DirectionalPreference.NEUTRAL and self.selection is not None:
            raise SignalValidationError("NEUTRAL direction cannot be an explicit selection")
        if any(not isinstance(item, SignalDiagnostic) for item in self.diagnostics):
            raise SignalValidationError("diagnostics must contain SignalDiagnostic values")
        if self.correlation_group is not None:
            _require_identifier(self.correlation_group, "correlation_group")

    def to_dict(self) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover
            raise TypeError("ModelSignal must serialize to a mapping")
        return value


@dataclass(frozen=True)
class AgreementDiagnostics:
    required_agreement_ratio: Decimal
    minimum_usable_models: int
    signal_statuses: tuple[SignalDiagnostic, ...]


@dataclass(frozen=True)
class AgreementResult:
    match_id: str
    market: MarketFamily
    candidate_selection: Selection
    candidate_line: Decimal | None
    supporting_model_count: int
    usable_model_count: int
    configured_model_count: int
    usable_agreement_ratio: Decimal | None
    configured_agreement_ratio: Decimal
    agreeing_models: tuple[ModelFamily, ...]
    conflicting_models: tuple[ModelFamily, ...]
    neutral_models: tuple[ModelFamily, ...]
    unavailable_models: tuple[ModelFamily, ...]
    sufficient_usable_models: bool
    meets_configured_agreement_ratio: bool
    diagnostics: AgreementDiagnostics

    def to_dict(self) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover
            raise TypeError("AgreementResult must serialize to a mapping")
        return value


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value
