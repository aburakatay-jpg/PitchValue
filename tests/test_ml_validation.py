from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.features.contracts import MatchStatus
from pitchvalue.ml import (
    DatasetBuilderConfig,
    DatasetRowProvenance,
    DiagnosticCode,
    FeatureKind,
    FeatureProfile,
    FeatureProvenance,
    FeatureRecord,
    FeatureSchema,
    MarketFeatureSemantics,
    MissingReason,
    ResolvedMatchOutcome,
    RowStatus,
    SourceMatchReference,
    TargetDefinition,
    TargetMode,
    TrainingCandidate,
    validate_candidate,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

KICKOFF = datetime(2026, 5, 2, 20, tzinfo=UTC)
AS_OF = datetime(2026, 5, 2, 10, tzinfo=UTC)
SCHEMA = FeatureSchema("v1", ("home_ppg", "away_ppg"), ("rest", "market_price"))
CONFIG = DatasetBuilderConfig(feature_schema=SCHEMA)


def _provenance(
    *sources: SourceMatchReference, result: bool = False, goals: bool = False
) -> FeatureProvenance:
    return FeatureProvenance(
        "feature-v1", "pitchvalue.features", "synthetic-v1", "calc-v1", sources, result, goals
    )


def _feature(name: str, value: object = Decimal("1.5"), **changes: object) -> FeatureRecord:
    values: dict[str, object] = {
        "name": name,
        "value": value,
        "available_at": AS_OF,
        "schema_version": "v1",
        "provenance": _provenance(
            SourceMatchReference(f"source-{name}", AS_OF - timedelta(days=2))
        ),
    }
    values.update(changes)
    return FeatureRecord(**values)  # type: ignore[arg-type]


def _candidate(
    features: tuple[FeatureRecord, ...] | None = None, **changes: object
) -> TrainingCandidate:
    values: dict[str, object] = {
        "match_id": "target-1",
        "competition_id": "EPL",
        "season_id": "2025-26",
        "kickoff": KICKOFF,
        "prediction_as_of": AS_OF,
        "target_definition": TargetDefinition(
            MarketFamily.MATCH_RESULT,
            TargetMode.MULTICLASS,
            (Selection.HOME, Selection.DRAW, Selection.AWAY),
        ),
        "outcome": ResolvedMatchOutcome("target-1", MatchStatus.FINISHED, 2, 1),
        "features": features or (_feature("home_ppg"), _feature("away_ppg")),
        "provenance": DatasetRowProvenance("synthetic-v1"),
    }
    values.update(changes)
    return TrainingCandidate(**values)  # type: ignore[arg-type]


def _codes(
    candidate: TrainingCandidate, config: DatasetBuilderConfig = CONFIG
) -> tuple[RowStatus, set[DiagnosticCode]]:
    status, diagnostics = validate_candidate(candidate, config)
    return status, {item.code for item in diagnostics}


def test_feature_available_before_and_exactly_at_as_of_are_legal() -> None:
    for instant in (AS_OF - timedelta(seconds=1), AS_OF):
        feature = replace(_feature("home_ppg"), available_at=instant)
        status, codes = _codes(_candidate((feature, _feature("away_ppg"))))
        assert status is RowStatus.READY
        assert DiagnosticCode.FEATURE_AVAILABLE_AFTER_AS_OF not in codes


def test_future_feature_and_later_recalculated_aggregate_rejected() -> None:
    for name in ("home_ppg", "away_ppg"):
        future = replace(_feature(name), available_at=AS_OF + timedelta(minutes=1))
        other = _feature("away_ppg" if name == "home_ppg" else "home_ppg")
        status, codes = _codes(_candidate((future, other)))
        assert status is RowStatus.LEAKAGE_DETECTED
        assert DiagnosticCode.FEATURE_AVAILABLE_AFTER_AS_OF in codes


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (
            SourceMatchReference("target-1", AS_OF - timedelta(days=1)),
            DiagnosticCode.TARGET_SELF_LEAKAGE,
        ),
        (SourceMatchReference("simultaneous", AS_OF), DiagnosticCode.SAME_TIME_SOURCE_MATCH),
        (
            SourceMatchReference("future", AS_OF + timedelta(seconds=1)),
            DiagnosticCode.FUTURE_SOURCE_MATCH,
        ),
    ],
)
def test_source_match_temporal_leakage(source: SourceMatchReference, code: DiagnosticCode) -> None:
    feature = replace(_feature("home_ppg"), provenance=_provenance(source))
    status, codes = _codes(_candidate((feature, _feature("away_ppg"))))
    assert status is RowStatus.LEAKAGE_DETECTED
    assert code in codes


@pytest.mark.parametrize("flag", ["result", "goals"])
def test_target_value_never_enters_features(flag: str) -> None:
    provenance = _provenance(result=flag == "result", goals=flag == "goals")
    feature = replace(_feature("home_ppg"), provenance=provenance)
    status, codes = _codes(_candidate((feature, _feature("away_ppg"))))
    assert status is RowStatus.LEAKAGE_DETECTED
    assert DiagnosticCode.TARGET_VALUE_IN_FEATURES in codes


def test_prediction_as_of_must_be_aware_and_strictly_before_kickoff() -> None:
    with pytest.raises(ValueError):
        _candidate(prediction_as_of=AS_OF.replace(tzinfo=None))
    with pytest.raises(ValueError):
        _candidate(prediction_as_of=KICKOFF)
    with pytest.raises(ValueError):
        _candidate(prediction_as_of=KICKOFF + timedelta(seconds=1))


def test_duplicate_unknown_and_version_mismatch_are_explicit() -> None:
    duplicate = (_feature("home_ppg"), _feature("home_ppg"), _feature("away_ppg"))
    status, codes = _codes(_candidate(duplicate))
    assert status is RowStatus.INVALID_FEATURE
    assert DiagnosticCode.DUPLICATE_FEATURE in codes
    status, codes = _codes(
        _candidate((_feature("home_ppg"), _feature("away_ppg"), _feature("unknown")))
    )
    assert status is RowStatus.SCHEMA_MISMATCH
    assert DiagnosticCode.UNKNOWN_FEATURE in codes
    wrong = replace(_feature("home_ppg"), schema_version="v2")
    status, codes = _codes(_candidate((wrong, _feature("away_ppg"))))
    assert status is RowStatus.SCHEMA_MISMATCH
    assert DiagnosticCode.FEATURE_VERSION_MISMATCH in codes


def test_required_missing_and_explicit_optional_missing() -> None:
    status, codes = _codes(_candidate((_feature("home_ppg"),)))
    assert status is RowStatus.MISSING_FEATURE
    assert DiagnosticCode.REQUIRED_FEATURE_MISSING in codes
    missing = _feature("rest", None, missing_reason=MissingReason.INSUFFICIENT_HISTORY)
    status, _ = _codes(_candidate((_feature("home_ppg"), _feature("away_ppg"), missing)))
    assert status is RowStatus.MISSING_FEATURE


def test_default_profile_rejects_market_feature_explicitly() -> None:
    odds = _feature(
        "market_price",
        Decimal("2.1"),
        kind=FeatureKind.MARKET_ODDS,
        market_semantics=MarketFeatureSemantics.DECIMAL_ODDS,
    )
    status, codes = _codes(_candidate((_feature("home_ppg"), _feature("away_ppg"), odds)))
    assert status is RowStatus.SCHEMA_MISMATCH
    assert DiagnosticCode.ODDS_FEATURE_NOT_ALLOWED_IN_BASELINE in codes


def test_odds_experiment_accepts_legal_price_and_rejects_future_closing_price() -> None:
    experiment = DatasetBuilderConfig(
        feature_schema=SCHEMA, feature_profile=FeatureProfile.ODDS_INCLUSIVE_EXPERIMENT
    )
    legal = _feature(
        "market_price",
        Decimal("2.1"),
        kind=FeatureKind.MARKET_ODDS,
        market_semantics=MarketFeatureSemantics.DECIMAL_ODDS,
    )
    assert (
        _codes(_candidate((_feature("home_ppg"), _feature("away_ppg"), legal)), experiment)[0]
        is RowStatus.READY
    )
    closing = replace(
        legal,
        available_at=datetime(2026, 5, 2, 19, 45, tzinfo=UTC),
        market_semantics=MarketFeatureSemantics.CLOSING_ODDS,
    )
    status, codes = _codes(
        _candidate((_feature("home_ppg"), _feature("away_ppg"), closing)), experiment
    )
    assert status is RowStatus.LEAKAGE_DETECTED
    assert DiagnosticCode.ODDS_AVAILABLE_AFTER_AS_OF in codes


def test_diagnostics_have_deterministic_order() -> None:
    bad = replace(_feature("unknown"), available_at=AS_OF + timedelta(hours=1), schema_version="v2")
    first = validate_candidate(_candidate((bad,)), CONFIG)
    second = validate_candidate(_candidate((bad,)), CONFIG)
    assert first == second
