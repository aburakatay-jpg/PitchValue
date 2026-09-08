"""Typed temporal contracts for leakage-safe model evaluation."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.evaluation.config import EvaluationValidationError, SplitStrategy
from pitchvalue.prediction.contracts import MarketFamily, Selection


class ObservationKind(StrEnum):
    MATCH = "MATCH"
    FEATURE = "FEATURE"
    ODDS = "ODDS"
    OUTCOME = "OUTCOME"


class OddsUse(StrEnum):
    PREDICTION_FEATURE = "PREDICTION_FEATURE"
    EVALUATION_REFERENCE = "EVALUATION_REFERENCE"
    CLOSING_REFERENCE = "CLOSING_REFERENCE"


class EvaluationStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_TRAINING_SAMPLE = "INSUFFICIENT_TRAINING_SAMPLE"
    INSUFFICIENT_TEST_SAMPLE = "INSUFFICIENT_TEST_SAMPLE"
    INVALID_TEMPORAL_ORDER = "INVALID_TEMPORAL_ORDER"
    LEAKAGE_DETECTED = "LEAKAGE_DETECTED"
    EMPTY_WINDOW = "EMPTY_WINDOW"
    INVALID_INPUT = "INVALID_INPUT"


class LeakageCode(StrEnum):
    TARGET_SELF_LEAKAGE = "TARGET_SELF_LEAKAGE"
    TARGET_RESULT_IN_FEATURES = "TARGET_RESULT_IN_FEATURES"
    FUTURE_OBSERVATION = "FUTURE_OBSERVATION"
    SAME_TIME_OBSERVATION = "SAME_TIME_OBSERVATION"
    FEATURE_AVAILABLE_AFTER_AS_OF = "FEATURE_AVAILABLE_AFTER_AS_OF"
    ODDS_AVAILABLE_AFTER_AS_OF = "ODDS_AVAILABLE_AFTER_AS_OF"
    OUTCOME_AVAILABLE_TOO_EARLY = "OUTCOME_AVAILABLE_TOO_EARLY"
    INVALID_AS_OF = "INVALID_AS_OF"


class FoldDiagnosticCode(StrEnum):
    EMPTY_TRAINING_WINDOW = "EMPTY_TRAINING_WINDOW"
    EMPTY_TEST_WINDOW = "EMPTY_TEST_WINDOW"
    INSUFFICIENT_TRAINING_SAMPLE = "INSUFFICIENT_TRAINING_SAMPLE"
    INSUFFICIENT_TEST_SAMPLE = "INSUFFICIENT_TEST_SAMPLE"


def _require_identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationValidationError(f"{name} is required")


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EvaluationValidationError(f"{name} must be timezone-aware")


def _validate_optional_market(
    market: MarketFamily | None, selection: Selection | None, line: Decimal | None
) -> None:
    if market is not None and not isinstance(market, MarketFamily):
        raise EvaluationValidationError("market must use MarketFamily")
    if selection is not None and not isinstance(selection, Selection):
        raise EvaluationValidationError("selection must use Selection")
    if selection is not None and market is None:
        raise EvaluationValidationError("selection requires market")
    if line is not None and (not isinstance(line, Decimal) or not line.is_finite()):
        raise EvaluationValidationError("line must be a finite Decimal")


class SerializableEvaluationContract:
    def to_dict(self) -> dict[str, Any]:
        value = _primitive(self)
        if not isinstance(value, dict):  # pragma: no cover - structural invariant
            raise TypeError("evaluation contract must serialize to a mapping")
        return value


@dataclass(frozen=True)
class TemporalObservation(SerializableEvaluationContract):
    observation_id: str
    match_id: str
    competition_id: str
    season_id: str
    kickoff: datetime
    available_at: datetime
    kind: ObservationKind = ObservationKind.MATCH
    source_id: str | None = None
    market: MarketFamily | None = None
    selection: Selection | None = None
    line: Decimal | None = None
    odds_use: OddsUse | None = None
    contains_target_outcome: bool = False

    def __post_init__(self) -> None:
        for name in ("observation_id", "match_id", "competition_id", "season_id"):
            _require_identifier(getattr(self, name), name)
        _require_aware(self.kickoff, "kickoff")
        _require_aware(self.available_at, "available_at")
        if not isinstance(self.kind, ObservationKind):
            raise EvaluationValidationError("kind must use ObservationKind")
        if self.source_id is not None:
            _require_identifier(self.source_id, "source_id")
        _validate_optional_market(self.market, self.selection, self.line)
        if self.odds_use is not None and not isinstance(self.odds_use, OddsUse):
            raise EvaluationValidationError("odds_use must use OddsUse")
        if self.odds_use is not None and self.kind is not ObservationKind.ODDS:
            raise EvaluationValidationError("odds_use is valid only for odds observations")
        if not isinstance(self.contains_target_outcome, bool):
            raise EvaluationValidationError("contains_target_outcome must be boolean")


@dataclass(frozen=True)
class EvaluationTarget(SerializableEvaluationContract):
    match_id: str
    competition_id: str
    season_id: str
    kickoff: datetime
    prediction_as_of: datetime
    market: MarketFamily | None = None
    selection: Selection | None = None
    line: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("match_id", "competition_id", "season_id"):
            _require_identifier(getattr(self, name), name)
        _require_aware(self.kickoff, "kickoff")
        _require_aware(self.prediction_as_of, "prediction_as_of")
        if self.prediction_as_of >= self.kickoff:
            raise EvaluationValidationError("prediction_as_of must be before kickoff")
        _validate_optional_market(self.market, self.selection, self.line)


@dataclass(frozen=True)
class EvaluationProvenance(SerializableEvaluationContract):
    model_name: str
    model_version: str
    feature_version: str | None = None
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.model_name, "model_name")
        _require_identifier(self.model_version, "model_version")
        if self.feature_version is not None:
            _require_identifier(self.feature_version, "feature_version")
        if any(not isinstance(value, str) or not value.strip() for value in self.source_ids):
            raise EvaluationValidationError("source_ids must contain non-empty strings")


@dataclass(frozen=True)
class PredictionEvaluationRecord(SerializableEvaluationContract):
    record_id: str
    target: EvaluationTarget
    fold_id: str
    provenance: EvaluationProvenance
    prediction_reference: str
    outcome_reference: str | None = None
    outcome_available_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("record_id", "fold_id", "prediction_reference"):
            _require_identifier(getattr(self, name), name)
        if not isinstance(self.target, EvaluationTarget):
            raise EvaluationValidationError("target must use EvaluationTarget")
        if not isinstance(self.provenance, EvaluationProvenance):
            raise EvaluationValidationError("provenance must use EvaluationProvenance")
        if (self.outcome_reference is None) != (self.outcome_available_at is None):
            raise EvaluationValidationError(
                "outcome_reference and outcome_available_at must be supplied together"
            )
        if self.outcome_reference is not None:
            _require_identifier(self.outcome_reference, "outcome_reference")
        if self.outcome_available_at is not None:
            _require_aware(self.outcome_available_at, "outcome_available_at")


@dataclass(frozen=True)
class LeakageDiagnostic(SerializableEvaluationContract):
    code: LeakageCode
    observation_id: str | None
    message: str


@dataclass(frozen=True)
class LeakageValidationResult(SerializableEvaluationContract):
    status: EvaluationStatus
    diagnostics: tuple[LeakageDiagnostic, ...]

    @property
    def is_valid(self) -> bool:
        return self.status is EvaluationStatus.READY


@dataclass(frozen=True)
class WalkForwardFold(SerializableEvaluationContract):
    fold_id: str
    strategy: SplitStrategy
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    training_observation_ids: tuple[str, ...]
    test_observation_ids: tuple[str, ...]
    status: EvaluationStatus
    diagnostics: tuple[FoldDiagnosticCode, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.fold_id, "fold_id")
        for name in ("train_start", "train_end", "test_start", "test_end"):
            _require_aware(getattr(self, name), name)
        if not self.train_start < self.train_end <= self.test_start < self.test_end:
            raise EvaluationValidationError("fold boundaries must be chronologically ordered")

    @property
    def training_observation_count(self) -> int:
        return len(self.training_observation_ids)

    @property
    def test_observation_count(self) -> int:
        return len(self.test_observation_ids)

    def to_dict(self) -> dict[str, Any]:
        value = super().to_dict()
        value["training_observation_count"] = self.training_observation_count
        value["test_observation_count"] = self.test_observation_count
        return value


@dataclass(frozen=True)
class FoldExecution(SerializableEvaluationContract):
    fold: WalkForwardFold
    training_observations: tuple[TemporalObservation, ...]
    test_observations: tuple[TemporalObservation, ...]


def _primitive(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value
