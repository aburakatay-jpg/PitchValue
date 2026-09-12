"""Typed features, candidates, rows, datasets, statuses, and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pitchvalue.features.contracts import MatchStatus
from pitchvalue.ml.config import FeatureProfile, MLDatasetValidationError, _identifier
from pitchvalue.ml.provenance import DatasetRowProvenance, FeatureProvenance, require_aware
from pitchvalue.prediction.contracts import MarketFamily, Selection

type FeatureScalar = Decimal | int | bool
type TargetScalar = Selection | bool


class FeatureKind(StrEnum):
    FOOTBALL_PERFORMANCE = "FOOTBALL_PERFORMANCE"
    MARKET_ODDS = "MARKET_ODDS"


class MarketFeatureSemantics(StrEnum):
    DECIMAL_ODDS = "DECIMAL_ODDS"
    RAW_IMPLIED_PROBABILITY = "RAW_IMPLIED_PROBABILITY"
    NO_VIG_PROBABILITY = "NO_VIG_PROBABILITY"
    CLOSING_ODDS = "CLOSING_ODDS"


class MissingReason(StrEnum):
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    FEATURE_UNAVAILABLE = "FEATURE_UNAVAILABLE"
    SOURCE_MISSING = "SOURCE_MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TargetMode(StrEnum):
    MULTICLASS = "MULTICLASS"
    BINARY = "BINARY"


class RowStatus(StrEnum):
    READY = "READY"
    MISSING_FEATURE = "MISSING_FEATURE"
    INVALID_FEATURE = "INVALID_FEATURE"
    LEAKAGE_DETECTED = "LEAKAGE_DETECTED"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    INVALID_TARGET = "INVALID_TARGET"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    DUPLICATE_ROW = "DUPLICATE_ROW"


class DatasetStatus(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    INVALID = "INVALID"


class DiagnosticCode(StrEnum):
    FEATURE_AVAILABLE_AFTER_AS_OF = "FEATURE_AVAILABLE_AFTER_AS_OF"
    TARGET_SELF_LEAKAGE = "TARGET_SELF_LEAKAGE"
    FUTURE_SOURCE_MATCH = "FUTURE_SOURCE_MATCH"
    SAME_TIME_SOURCE_MATCH = "SAME_TIME_SOURCE_MATCH"
    TARGET_VALUE_IN_FEATURES = "TARGET_VALUE_IN_FEATURES"
    REQUIRED_FEATURE_MISSING = "REQUIRED_FEATURE_MISSING"
    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"
    DUPLICATE_FEATURE = "DUPLICATE_FEATURE"
    FEATURE_VERSION_MISMATCH = "FEATURE_VERSION_MISMATCH"
    INVALID_TARGET = "INVALID_TARGET"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    DUPLICATE_TRAINING_ROW = "DUPLICATE_TRAINING_ROW"
    ODDS_FEATURE_NOT_ALLOWED_IN_BASELINE = "ODDS_FEATURE_NOT_ALLOWED_IN_BASELINE"
    ODDS_AVAILABLE_AFTER_AS_OF = "ODDS_AVAILABLE_AFTER_AS_OF"


@dataclass(frozen=True)
class FeatureRecord:
    name: str
    value: FeatureScalar | None
    available_at: datetime
    schema_version: str
    provenance: FeatureProvenance
    kind: FeatureKind = FeatureKind.FOOTBALL_PERFORMANCE
    missing_reason: MissingReason | None = None
    market_semantics: MarketFeatureSemantics | None = None

    def __post_init__(self) -> None:
        _identifier(self.name, "feature name")
        _identifier(self.schema_version, "schema_version")
        require_aware(self.available_at, "available_at")
        if not isinstance(self.provenance, FeatureProvenance):
            raise MLDatasetValidationError("provenance must use FeatureProvenance")
        if not isinstance(self.kind, FeatureKind):
            raise MLDatasetValidationError("kind must use FeatureKind")
        if self.kind is FeatureKind.MARKET_ODDS:
            if not isinstance(self.market_semantics, MarketFeatureSemantics):
                raise MLDatasetValidationError("market feature requires explicit market_semantics")
        elif self.market_semantics is not None:
            raise MLDatasetValidationError("market_semantics is valid only for market features")
        if self.value is None:
            if not isinstance(self.missing_reason, MissingReason):
                raise MLDatasetValidationError("missing feature requires missing_reason")
        elif self.missing_reason is not None:
            raise MLDatasetValidationError("available feature cannot have missing_reason")
        elif isinstance(self.value, (float, str)):
            raise MLDatasetValidationError("feature value must be Decimal, integer, or boolean")
        elif not isinstance(self.value, (Decimal, int, bool)):
            raise MLDatasetValidationError("unsupported feature value")
        elif isinstance(self.value, Decimal) and not self.value.is_finite():
            raise MLDatasetValidationError("Decimal feature must be finite")

    def to_dict(self) -> dict[str, Any]:
        return _primitive(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class TargetDefinition:
    market: MarketFamily
    mode: TargetMode
    classes: tuple[Selection, ...]
    line: Decimal | None = None
    selection: Selection | None = None
    version: str = "v1"

    def __post_init__(self) -> None:
        _identifier(self.version, "target version")
        if not isinstance(self.market, MarketFamily) or not isinstance(self.mode, TargetMode):
            raise MLDatasetValidationError("target market and mode must use canonical enums")
        if any(not isinstance(item, Selection) for item in self.classes):
            raise MLDatasetValidationError("target classes must use Selection")
        if len(self.classes) != len(set(self.classes)):
            raise MLDatasetValidationError("duplicate target classes")
        if self.line is not None and (
            not isinstance(self.line, Decimal) or not self.line.is_finite()
        ):
            raise MLDatasetValidationError("target line must be a finite Decimal")
        _validate_target_definition(self)

    @property
    def identity(self) -> str:
        selection = self.selection.value if self.selection else "-"
        line = str(self.line) if self.line is not None else "-"
        return f"{self.market.value}:{self.mode.value}:{selection}:{line}:{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return _primitive(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ResolvedMatchOutcome:
    match_id: str
    status: MatchStatus
    home_goals: int | None
    away_goals: int | None

    def __post_init__(self) -> None:
        _identifier(self.match_id, "outcome match_id")
        if not isinstance(self.status, MatchStatus):
            raise MLDatasetValidationError("status must use MatchStatus")
        for name in ("home_goals", "away_goals"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise MLDatasetValidationError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class TrainingCandidate:
    match_id: str
    competition_id: str
    season_id: str
    kickoff: datetime
    prediction_as_of: datetime
    target_definition: TargetDefinition
    outcome: ResolvedMatchOutcome
    features: tuple[FeatureRecord, ...]
    provenance: DatasetRowProvenance

    def __post_init__(self) -> None:
        for name in ("match_id", "competition_id", "season_id"):
            _identifier(getattr(self, name), name)
        require_aware(self.kickoff, "kickoff")
        require_aware(self.prediction_as_of, "prediction_as_of")
        if self.prediction_as_of >= self.kickoff:
            raise MLDatasetValidationError("prediction_as_of must be strictly before kickoff")
        if self.outcome.match_id != self.match_id:
            raise MLDatasetValidationError("outcome must belong to candidate match")

    @property
    def identity(self) -> str:
        return (
            f"{self.match_id}|{self.target_definition.identity}|{self.prediction_as_of.isoformat()}"
        )


@dataclass(frozen=True)
class DatasetDiagnostic:
    code: DiagnosticCode
    row_identity: str
    feature_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _primitive(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class TrainingRow:
    row_id: str
    match_id: str
    competition_id: str
    season_id: str
    kickoff: datetime
    prediction_as_of: datetime
    feature_schema_version: str
    feature_profile: FeatureProfile
    target_definition: TargetDefinition
    target_value: TargetScalar
    features: tuple[FeatureRecord, ...]
    provenance: DatasetRowProvenance
    status: RowStatus
    diagnostics: tuple[DatasetDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _primitive(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class PredictionFeatureRow:
    """Outcome-free feature row accepted only by model inference."""

    row_id: str
    match_id: str
    competition_id: str
    season_id: str
    kickoff: datetime
    prediction_as_of: datetime
    feature_schema_version: str
    feature_profile: FeatureProfile
    features: tuple[FeatureRecord, ...]

    def __post_init__(self) -> None:
        for name in ("row_id", "match_id", "competition_id", "season_id"):
            _identifier(getattr(self, name), name)
        require_aware(self.kickoff, "kickoff")
        require_aware(self.prediction_as_of, "prediction_as_of")
        if self.prediction_as_of >= self.kickoff:
            raise MLDatasetValidationError("prediction_as_of must be strictly before kickoff")

    def to_dict(self) -> dict[str, Any]:
        return _primitive(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class RejectedTrainingRow:
    row_identity: str
    status: RowStatus
    diagnostics: tuple[DatasetDiagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return _primitive(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class MLDataset:
    dataset_version: str
    feature_schema_version: str
    feature_profile: FeatureProfile
    target_definitions: tuple[TargetDefinition, ...]
    rows: tuple[TrainingRow, ...]
    rejected_rows: tuple[RejectedTrainingRow, ...]
    input_candidate_count: int
    ready_row_count: int
    missing_row_count: int
    rejected_row_count: int
    leakage_rejection_count: int
    schema_rejection_count: int
    target_rejection_count: int
    status: DatasetStatus

    def to_dict(self) -> dict[str, Any]:
        return _primitive(self)  # type: ignore[return-value]


def _validate_target_definition(target: TargetDefinition) -> None:
    binary = (Selection.OVER, Selection.UNDER)
    if target.market is MarketFamily.MATCH_RESULT:
        valid = (
            target.mode is TargetMode.MULTICLASS
            and target.classes == (Selection.HOME, Selection.DRAW, Selection.AWAY)
            and target.line is None
            and target.selection is None
        )
    elif target.market is MarketFamily.BTTS:
        valid = (
            target.mode is TargetMode.MULTICLASS
            and target.classes == (Selection.YES, Selection.NO)
            and target.line is None
            and target.selection is None
        )
    elif target.market is MarketFamily.TOTAL_GOALS:
        valid = (
            target.mode is TargetMode.MULTICLASS
            and target.classes == binary
            and target.line in (Decimal("1.5"), Decimal("2.5"))
            and target.selection is None
        )
    elif target.market in (MarketFamily.HOME_TEAM_TOTAL, MarketFamily.AWAY_TEAM_TOTAL):
        valid = (
            target.mode is TargetMode.MULTICLASS
            and target.classes == binary
            and target.line in (Decimal("0.5"), Decimal("1.5"))
            and target.selection is None
        )
    elif target.market is MarketFamily.DOUBLE_CHANCE:
        valid = (
            target.mode is TargetMode.BINARY
            and target.classes == ()
            and target.line is None
            and target.selection in (Selection.ONE_X, Selection.X_TWO, Selection.ONE_TWO)
        )
    else:
        valid = False
    if not valid:
        raise MLDatasetValidationError("invalid V1 target definition")


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    return value
