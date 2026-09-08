from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.features.contracts import MatchStatus
from pitchvalue.ml import (
    DatasetBuilderConfig,
    DatasetRowProvenance,
    DatasetStatus,
    DiagnosticCode,
    FeatureProvenance,
    FeatureRecord,
    FeatureSchema,
    MissingReason,
    MissingValuePolicy,
    ResolvedMatchOutcome,
    RowStatus,
    SourceMatchReference,
    TargetDefinition,
    TargetMode,
    TrainingCandidate,
    build_dataset,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

BASE = datetime(2026, 4, 1, tzinfo=UTC)
SCHEMA = FeatureSchema("v1", ("home_form", "away_form"), ("rest",))
CONFIG = DatasetBuilderConfig(feature_schema=SCHEMA)


def _target(
    market: MarketFamily = MarketFamily.MATCH_RESULT, line: Decimal | None = None
) -> TargetDefinition:
    if market is MarketFamily.MATCH_RESULT:
        return TargetDefinition(
            market, TargetMode.MULTICLASS, (Selection.HOME, Selection.DRAW, Selection.AWAY)
        )
    if market is MarketFamily.BTTS:
        return TargetDefinition(market, TargetMode.MULTICLASS, (Selection.YES, Selection.NO))
    return TargetDefinition(market, TargetMode.MULTICLASS, (Selection.OVER, Selection.UNDER), line)


def _feature(
    name: str, value: object = Decimal("1.25"), available_at: datetime | None = None
) -> FeatureRecord:
    instant = available_at or BASE
    provenance = FeatureProvenance(
        "feature-v1",
        "pitchvalue.features",
        "synthetic-v1",
        f"calc-{name}",
        (SourceMatchReference(f"source-{name}", instant - timedelta(days=1)),),
    )
    return FeatureRecord(name, value, instant, "v1", provenance)  # type: ignore[arg-type]


def _candidate(
    match_id: str = "match-1",
    *,
    kickoff_days: int = 2,
    target: TargetDefinition | None = None,
    as_of: datetime | None = None,
    features: tuple[FeatureRecord, ...] | None = None,
    status: MatchStatus = MatchStatus.FINISHED,
) -> TrainingCandidate:
    kickoff = BASE + timedelta(days=kickoff_days)
    return TrainingCandidate(
        match_id,
        "EPL",
        "2025-26",
        kickoff,
        as_of or kickoff - timedelta(hours=6),
        target or _target(),
        ResolvedMatchOutcome(match_id, status, 2, 1),
        features or (_feature("home_form"), _feature("away_form")),
        DatasetRowProvenance("synthetic-v1"),
    )


def test_empty_dataset_is_explicit() -> None:
    result = build_dataset((), CONFIG)
    assert result.status is DatasetStatus.EMPTY
    assert result.input_candidate_count == result.ready_row_count == result.rejected_row_count == 0


def test_valid_row_preserves_identity_scope_target_and_provenance() -> None:
    result = build_dataset((_candidate(),), CONFIG)
    row = result.rows[0]
    assert result.status is DatasetStatus.READY
    assert (row.match_id, row.competition_id, row.season_id) == ("match-1", "EPL", "2025-26")
    assert row.kickoff == BASE + timedelta(days=2)
    assert row.prediction_as_of < row.kickoff
    assert row.feature_schema_version == "v1"
    assert row.target_definition.market is MarketFamily.MATCH_RESULT
    assert row.target_value is Selection.HOME
    assert row.provenance.source_version == "synthetic-v1"
    assert row.status is RowStatus.READY


def test_home_away_orientation_is_preserved() -> None:
    features = (_feature("away_form", Decimal("0.75")), _feature("home_form", Decimal("2.25")))
    row = build_dataset((_candidate(features=features),), CONFIG).rows[0]
    assert [(item.name, item.value) for item in row.features] == [
        ("home_form", Decimal("2.25")),
        ("away_form", Decimal("0.75")),
    ]


def test_shuffled_candidates_and_features_produce_same_dataset() -> None:
    first = _candidate(
        "match-b", kickoff_days=3, features=(_feature("away_form"), _feature("home_form"))
    )
    second = _candidate("match-a", kickoff_days=2)
    forward = build_dataset((first, second), CONFIG)
    reverse = build_dataset(
        (second, replace(first, features=tuple(reversed(first.features)))), CONFIG
    )
    assert forward.to_dict() == reverse.to_dict()


def test_dataset_and_rows_are_immutable_and_serialization_is_stable() -> None:
    dataset = build_dataset((_candidate(),), CONFIG)
    assert dataset.to_dict() == dataset.to_dict()
    with pytest.raises(FrozenInstanceError):
        dataset.status = DatasetStatus.INVALID  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        dataset.rows[0].match_id = "changed"  # type: ignore[misc]


def test_exact_duplicate_rows_are_all_rejected() -> None:
    candidate = _candidate()
    result = build_dataset((candidate, candidate), CONFIG)
    assert result.status is DatasetStatus.INVALID
    assert result.rejected_row_count == 2
    assert all(row.status is RowStatus.DUPLICATE_ROW for row in result.rejected_rows)
    assert all(
        row.diagnostics[0].code is DiagnosticCode.DUPLICATE_TRAINING_ROW
        for row in result.rejected_rows
    )


def test_same_match_different_market_line_and_as_of_are_distinct() -> None:
    base = _candidate()
    btts = _candidate(target=_target(MarketFamily.BTTS))
    total_15 = _candidate(target=_target(MarketFamily.TOTAL_GOALS, Decimal("1.5")))
    total_25 = _candidate(target=_target(MarketFamily.TOTAL_GOALS, Decimal("2.5")))
    earlier = _candidate(as_of=base.prediction_as_of - timedelta(hours=1))
    result = build_dataset((base, btts, total_15, total_25, earlier), CONFIG)
    assert result.ready_row_count == 5
    assert len({row.row_id for row in result.rows}) == 5


def test_schema_version_participates_in_deterministic_row_id() -> None:
    row_v1 = build_dataset((_candidate(),), CONFIG).rows[0]
    feature_v2 = tuple(replace(item, schema_version="v2") for item in _candidate().features)
    config_v2 = DatasetBuilderConfig(feature_schema=FeatureSchema("v2", ("home_form", "away_form")))
    row_v2 = build_dataset((_candidate(features=feature_v2),), config_v2).rows[0]
    assert row_v1.row_id != row_v2.row_id


def test_preserve_missing_retains_explicit_none_without_imputation() -> None:
    missing = FeatureRecord(
        "home_form",
        None,
        BASE,
        "v1",
        FeatureProvenance("feature-v1", "pitchvalue.features", "synthetic-v1", "missing"),
        missing_reason=MissingReason.INSUFFICIENT_HISTORY,
    )
    result = build_dataset((_candidate(features=(missing, _feature("away_form"))),), CONFIG)
    assert result.status is DatasetStatus.PARTIAL
    assert result.missing_row_count == 1
    assert result.rows[0].features[0].value is None
    assert result.rows[0].features[0].missing_reason is MissingReason.INSUFFICIENT_HISTORY


def test_preserve_policy_does_not_invent_absent_required_feature() -> None:
    result = build_dataset((_candidate(features=(_feature("home_form"),)),), CONFIG)
    assert result.status is DatasetStatus.INVALID
    assert result.rejected_rows[0].status is RowStatus.MISSING_FEATURE
    assert result.rows == ()


def test_reject_missing_policy_rejects_required_but_allows_optional_missing() -> None:
    reject = DatasetBuilderConfig(
        feature_schema=SCHEMA, missing_value_policy=MissingValuePolicy.REJECT_ROW
    )
    required_missing = _candidate(features=(_feature("home_form"),))
    assert (
        build_dataset((required_missing,), reject).rejected_rows[0].status
        is RowStatus.MISSING_FEATURE
    )
    optional = FeatureRecord(
        "rest",
        None,
        BASE,
        "v1",
        FeatureProvenance("feature-v1", "pitchvalue.features", "synthetic-v1", "missing-rest"),
        missing_reason=MissingReason.NOT_APPLICABLE,
    )
    result = build_dataset(
        (_candidate(features=(_feature("home_form"), _feature("away_form"), optional)),), reject
    )
    assert result.missing_row_count == 1
    assert result.rejected_row_count == 0


def test_partial_dataset_counts_leakage_schema_and_target_rejections() -> None:
    future = _feature("home_form", available_at=BASE + timedelta(days=3))
    leaked = _candidate("leak", features=(future, _feature("away_form")))
    unknown = _candidate(
        "schema", features=(_feature("home_form"), _feature("away_form"), _feature("extra"))
    )
    unresolved = _candidate("target", status=MatchStatus.SCHEDULED)
    result = build_dataset((_candidate("ready"), leaked, unknown, unresolved), CONFIG)
    assert result.status is DatasetStatus.PARTIAL
    assert (result.ready_row_count, result.rejected_row_count) == (1, 3)
    assert (
        result.leakage_rejection_count,
        result.schema_rejection_count,
        result.target_rejection_count,
    ) == (1, 1, 1)


def test_builder_does_not_mutate_inputs() -> None:
    candidate = _candidate(features=(_feature("away_form"), _feature("home_form")))
    before = candidate.features
    build_dataset((candidate,), CONFIG)
    assert candidate.features == before
