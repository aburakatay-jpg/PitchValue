from dataclasses import replace
from datetime import UTC, datetime, timedelta

from pitchvalue.features.config import FeatureConfig
from pitchvalue.features.contracts import (
    HistoricalMatch,
    MatchFeatures,
    MatchStatus,
    TargetFixture,
)
from pitchvalue.features.engine import compute_match_features
from pitchvalue.models.poisson.config import (
    DEFAULT_POISSON_CONFIG,
    PartialHistoryPolicy,
)
from pitchvalue.models.poisson.contracts import PoissonModelStatus
from pitchvalue.models.poisson.model import analyze_poisson, input_from_match_features

NOW = datetime(2026, 9, 10, 18, tzinfo=UTC)


def target() -> TargetFixture:
    return TargetFixture("target", "league", "s1", NOW, "A", "B")


def match(
    match_id: str, days: int, home: str, away: str, home_score: int, away_score: int
) -> HistoricalMatch:
    return HistoricalMatch(
        match_id,
        "league",
        "s1",
        NOW - timedelta(days=days),
        home,
        away,
        MatchStatus.FINISHED,
        home_score,
        away_score,
    )


def complete_features() -> MatchFeatures:
    config = FeatureConfig(
        recent_window=1,
        extended_window=1,
        home_split_window=1,
        away_split_window=1,
    )
    return compute_match_features(
        target(),
        [match("home", 5, "A", "X", 2, 1), match("away", 4, "Y", "B", 1, 1)],
        config,
    )


def test_complete_features_adapt_to_ready_poisson_input() -> None:
    features = complete_features()
    model_input = input_from_match_features(features)
    analysis = analyze_poisson(model_input)
    assert analysis.status is PoissonModelStatus.READY
    assert analysis.strengths is not None
    assert not analysis.diagnostics.partial_history_used  # type: ignore[union-attr]


def test_partial_features_are_allowed_and_exposed_by_default() -> None:
    features = compute_match_features(
        target(),
        [match("home", 5, "A", "X", 2, 1), match("away", 4, "Y", "B", 1, 1)],
    )
    analysis = analyze_poisson(input_from_match_features(features))
    assert analysis.status is PoissonModelStatus.READY
    assert analysis.diagnostics.partial_history_used  # type: ignore[union-attr]


def test_complete_history_policy_rejects_partial_venue_windows() -> None:
    features = compute_match_features(
        target(),
        [match("home", 5, "A", "X", 2, 1), match("away", 4, "Y", "B", 1, 1)],
    )
    config = replace(
        DEFAULT_POISSON_CONFIG,
        partial_history_policy=PartialHistoryPolicy.REQUIRE_COMPLETE,
    )
    analysis = analyze_poisson(input_from_match_features(features), config)
    assert analysis.status is PoissonModelStatus.INPUT_INSUFFICIENT
    assert "COMPLETE_HISTORY_REQUIRED" in analysis.reasons


def test_missing_venue_rates_produce_input_insufficient() -> None:
    features = compute_match_features(target(), [match("away", 4, "Y", "B", 1, 1)])
    analysis = analyze_poisson(input_from_match_features(features))
    assert analysis.status is PoissonModelStatus.INPUT_INSUFFICIENT
    assert "home_team_home_goals_for_per_match" in analysis.reasons


def test_missing_league_baseline_produces_input_insufficient() -> None:
    features = compute_match_features(target(), [])
    analysis = analyze_poisson(input_from_match_features(features))
    assert analysis.status is PoissonModelStatus.INPUT_INSUFFICIENT
    assert "league_home_goals_per_match" in analysis.reasons


def test_adapter_and_analysis_do_not_mutate_features_or_input() -> None:
    features = complete_features()
    before = features.to_dict()
    model_input = input_from_match_features(features)
    input_before = model_input
    first = analyze_poisson(model_input)
    second = analyze_poisson(model_input)
    assert first == second
    assert first.to_dict() == second.to_dict()
    assert first.to_dict()["status"] == "READY"
    assert model_input == input_before
    assert features.to_dict() == before


def test_analysis_serialization_is_deterministic_and_contains_no_publication_fields() -> None:
    analysis = analyze_poisson(input_from_match_features(complete_features()))
    serialized = analysis.to_dict()
    assert serialized == analysis.to_dict()
    assert serialized["status"] == "READY"
    assert "odds" not in serialized
    assert "edge" not in serialized
    assert "publication_eligible" not in serialized
