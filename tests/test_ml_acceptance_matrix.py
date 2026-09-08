from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pitchvalue.features.contracts import MatchStatus
from pitchvalue.ml import (
    DatasetBuilderConfig,
    DatasetRowProvenance,
    DiagnosticCode,
    FeatureProfile,
    FeatureProvenance,
    FeatureRecord,
    FeatureSchema,
    MissingReason,
    ResolvedMatchOutcome,
    SourceMatchReference,
    TargetDefinition,
    TargetMode,
    TrainingCandidate,
    build_dataset,
)
from pitchvalue.prediction.contracts import MarketFamily, Selection

NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "target",
    [
        TargetDefinition(
            MarketFamily.MATCH_RESULT,
            TargetMode.MULTICLASS,
            (Selection.HOME, Selection.DRAW, Selection.AWAY),
        ),
        TargetDefinition(MarketFamily.BTTS, TargetMode.MULTICLASS, (Selection.YES, Selection.NO)),
        TargetDefinition(
            MarketFamily.TOTAL_GOALS,
            TargetMode.MULTICLASS,
            (Selection.OVER, Selection.UNDER),
            Decimal("1.5"),
        ),
        TargetDefinition(
            MarketFamily.TOTAL_GOALS,
            TargetMode.MULTICLASS,
            (Selection.OVER, Selection.UNDER),
            Decimal("2.5"),
        ),
        TargetDefinition(
            MarketFamily.HOME_TEAM_TOTAL,
            TargetMode.MULTICLASS,
            (Selection.OVER, Selection.UNDER),
            Decimal("0.5"),
        ),
        TargetDefinition(
            MarketFamily.HOME_TEAM_TOTAL,
            TargetMode.MULTICLASS,
            (Selection.OVER, Selection.UNDER),
            Decimal("1.5"),
        ),
        TargetDefinition(
            MarketFamily.AWAY_TEAM_TOTAL,
            TargetMode.MULTICLASS,
            (Selection.OVER, Selection.UNDER),
            Decimal("0.5"),
        ),
        TargetDefinition(
            MarketFamily.AWAY_TEAM_TOTAL,
            TargetMode.MULTICLASS,
            (Selection.OVER, Selection.UNDER),
            Decimal("1.5"),
        ),
        TargetDefinition(
            MarketFamily.DOUBLE_CHANCE,
            TargetMode.BINARY,
            (),
            selection=Selection.ONE_X,
        ),
        TargetDefinition(
            MarketFamily.DOUBLE_CHANCE,
            TargetMode.BINARY,
            (),
            selection=Selection.X_TWO,
        ),
        TargetDefinition(
            MarketFamily.DOUBLE_CHANCE,
            TargetMode.BINARY,
            (),
            selection=Selection.ONE_TWO,
        ),
    ],
)
def test_every_v1_target_contract_is_representable(target: TargetDefinition) -> None:
    assert target.identity
    assert target.to_dict()["market"] == target.market.value


@pytest.mark.parametrize(
    ("market", "line"),
    [
        (MarketFamily.TOTAL_GOALS, Decimal("1.50")),
        (MarketFamily.TOTAL_GOALS, Decimal("2.500")),
        (MarketFamily.HOME_TEAM_TOTAL, Decimal("0.50")),
        (MarketFamily.HOME_TEAM_TOTAL, Decimal("1.500")),
        (MarketFamily.AWAY_TEAM_TOTAL, Decimal("0.500")),
        (MarketFamily.AWAY_TEAM_TOTAL, Decimal("1.50")),
    ],
)
def test_decimal_target_lines_use_numeric_equality(market: MarketFamily, line: Decimal) -> None:
    target = TargetDefinition(
        market, TargetMode.MULTICLASS, (Selection.OVER, Selection.UNDER), line
    )
    assert target.line == line.normalize()


@pytest.mark.parametrize(
    "reason",
    [
        MissingReason.INSUFFICIENT_HISTORY,
        MissingReason.FEATURE_UNAVAILABLE,
        MissingReason.SOURCE_MISSING,
        MissingReason.NOT_APPLICABLE,
    ],
)
def test_all_missing_reasons_are_preserved(reason: MissingReason) -> None:
    feature = FeatureRecord(
        "missing",
        None,
        NOW,
        "v1",
        FeatureProvenance("v1", "features", "synthetic", "calc"),
        missing_reason=reason,
    )
    assert feature.to_dict()["missing_reason"] == reason.value
    assert feature.to_dict()["value"] is None


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("1.2500"), -2, 0, 7, True, False])
def test_supported_feature_scalars_serialize_stably(value: Decimal | int | bool) -> None:
    feature = FeatureRecord(
        "value", value, NOW, "v1", FeatureProvenance("v1", "features", "synthetic", "calc")
    )
    assert feature.to_dict() == feature.to_dict()
    assert not isinstance(feature.to_dict()["value"], float)


@pytest.mark.parametrize(
    "code",
    [
        DiagnosticCode.FEATURE_AVAILABLE_AFTER_AS_OF,
        DiagnosticCode.TARGET_SELF_LEAKAGE,
        DiagnosticCode.FUTURE_SOURCE_MATCH,
        DiagnosticCode.SAME_TIME_SOURCE_MATCH,
        DiagnosticCode.TARGET_VALUE_IN_FEATURES,
        DiagnosticCode.REQUIRED_FEATURE_MISSING,
        DiagnosticCode.UNKNOWN_FEATURE,
        DiagnosticCode.DUPLICATE_FEATURE,
        DiagnosticCode.FEATURE_VERSION_MISMATCH,
        DiagnosticCode.INVALID_TARGET,
        DiagnosticCode.TARGET_UNAVAILABLE,
        DiagnosticCode.DUPLICATE_TRAINING_ROW,
        DiagnosticCode.ODDS_FEATURE_NOT_ALLOWED_IN_BASELINE,
        DiagnosticCode.ODDS_AVAILABLE_AFTER_AS_OF,
    ],
)
def test_diagnostic_reason_codes_are_explicit_and_stable(code: DiagnosticCode) -> None:
    assert code.value == code.name


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ((MarketFamily.TOTAL_GOALS, Decimal("1.5")), (MarketFamily.TOTAL_GOALS, Decimal("2.5"))),
        (
            (MarketFamily.TOTAL_GOALS, Decimal("1.5")),
            (MarketFamily.HOME_TEAM_TOTAL, Decimal("1.5")),
        ),
        (
            (MarketFamily.HOME_TEAM_TOTAL, Decimal("0.5")),
            (MarketFamily.AWAY_TEAM_TOTAL, Decimal("0.5")),
        ),
    ],
)
def test_target_market_and_line_participate_in_identity(
    left: tuple[MarketFamily, Decimal], right: tuple[MarketFamily, Decimal]
) -> None:
    def make(value: tuple[MarketFamily, Decimal]) -> TargetDefinition:
        return TargetDefinition(
            value[0], TargetMode.MULTICLASS, (Selection.OVER, Selection.UNDER), value[1]
        )

    assert make(left).identity != make(right).identity


@pytest.mark.parametrize(
    ("competition", "season"),
    [("EPL", "2025-26"), ("LL", "2024-25"), ("SA", "2023-24")],
)
def test_dataset_rows_preserve_competition_and_season_scope(competition: str, season: str) -> None:
    kickoff = NOW + timedelta(days=1)
    target = TargetDefinition(
        MarketFamily.MATCH_RESULT,
        TargetMode.MULTICLASS,
        (Selection.HOME, Selection.DRAW, Selection.AWAY),
    )
    features = (
        FeatureRecord(
            "form",
            Decimal("1.5"),
            NOW,
            "v1",
            FeatureProvenance(
                "v1",
                "features",
                "synthetic",
                "calc",
                (SourceMatchReference("source", NOW - timedelta(days=1)),),
            ),
        ),
    )
    candidate = TrainingCandidate(
        f"{competition}-{season}",
        competition,
        season,
        kickoff,
        NOW,
        target,
        ResolvedMatchOutcome(f"{competition}-{season}", MatchStatus.FINISHED, 1, 0),
        features,
        DatasetRowProvenance("synthetic"),
    )
    dataset = build_dataset(
        (candidate,), DatasetBuilderConfig(feature_schema=FeatureSchema("v1", ("form",)))
    )
    assert (dataset.rows[0].competition_id, dataset.rows[0].season_id) == (
        competition,
        season,
    )


@pytest.mark.parametrize("profile", list(FeatureProfile))
def test_feature_profiles_have_deterministic_config_serialization(
    profile: FeatureProfile,
) -> None:
    config = DatasetBuilderConfig(feature_profile=profile)
    assert config.to_dict()["feature_profile"] == profile.value
