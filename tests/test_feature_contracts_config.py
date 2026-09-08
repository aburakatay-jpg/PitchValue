from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pitchvalue.features.config import (
    DEFAULT_FEATURE_CONFIG,
    FeatureConfig,
    SeasonHistoryScope,
)
from pitchvalue.features.contracts import (
    FeatureValidationError,
    HistoricalMatch,
    MatchStatus,
    OptionalMatchStatistics,
    TargetFixture,
)

NOW = datetime(2026, 9, 8, 18, tzinfo=UTC)


def valid_match(**overrides: object) -> HistoricalMatch:
    values: dict[str, object] = {
        "match_id": "m1",
        "competition_id": "c1",
        "season_id": "s1",
        "kickoff": NOW,
        "home_team_id": "home",
        "away_team_id": "away",
        "status": MatchStatus.FINISHED,
        "home_score": 2,
        "away_score": 1,
    }
    values.update(overrides)
    return HistoricalMatch(**values)  # type: ignore[arg-type]


def test_historical_and_target_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(FeatureValidationError, match="timezone-aware"):
        valid_match(kickoff=NOW.replace(tzinfo=None))
    with pytest.raises(FeatureValidationError, match="timezone-aware"):
        TargetFixture("t", "c1", "s1", NOW.replace(tzinfo=None), "home", "away")


@pytest.mark.parametrize("field", ["match_id", "competition_id", "season_id", "home_team_id"])
def test_required_match_identifiers_cannot_be_blank(field: str) -> None:
    with pytest.raises(FeatureValidationError, match="required"):
        valid_match(**{field: " "})


def test_invalid_same_team_match_is_rejected() -> None:
    with pytest.raises(FeatureValidationError, match="must differ"):
        valid_match(away_team_id="home")


@pytest.mark.parametrize("score", [-1, True])
def test_invalid_score_is_rejected(score: object) -> None:
    with pytest.raises(FeatureValidationError, match="home_score"):
        valid_match(home_score=score)


def test_incomplete_finished_match_is_rejected() -> None:
    with pytest.raises(FeatureValidationError, match="present together"):
        valid_match(home_score=None)
    with pytest.raises(FeatureValidationError, match="require normal-time"):
        valid_match(home_score=None, away_score=None)


def test_optional_statistics_preserve_missing_values_and_reject_negative_values() -> None:
    stats = OptionalMatchStatistics(home_shots=0, away_shots=None)
    assert stats.home_shots == 0
    assert stats.away_shots is None
    with pytest.raises(FeatureValidationError, match="home_corners"):
        OptionalMatchStatistics(home_corners=-1)


def test_target_contract_has_no_score_or_result_fields() -> None:
    target = TargetFixture("t", "c1", "s1", NOW, "home", "away")
    assert not hasattr(target, "home_score")
    assert not hasattr(target, "result")


def test_prediction_cutoff_cannot_be_after_kickoff() -> None:
    with pytest.raises(FeatureValidationError, match="cannot be after"):
        TargetFixture(
            "t",
            "c1",
            "s1",
            NOW,
            "home",
            "away",
            as_of=NOW.replace(hour=19),
        )


def test_default_feature_config_and_serialization() -> None:
    assert DEFAULT_FEATURE_CONFIG.recent_window == 5
    assert DEFAULT_FEATURE_CONFIG.extended_window == 10
    assert DEFAULT_FEATURE_CONFIG.home_split_window == 5
    assert DEFAULT_FEATURE_CONFIG.away_split_window == 5
    assert DEFAULT_FEATURE_CONFIG.schedule_density_windows_days == (7, 14)
    assert DEFAULT_FEATURE_CONFIG.as_dict()["season_history_scope"] == "CURRENT_SEASON_ONLY"


@pytest.mark.parametrize(
    "overrides",
    [
        {"recent_window": 0},
        {"extended_window": -1},
        {"home_split_window": True},
        {"recent_window": 11},
        {"schedule_density_windows_days": ()},
        {"schedule_density_windows_days": (7, 7)},
        {"schedule_density_windows_days": (14, 7)},
        {"schedule_density_windows_days": (0, 7)},
        {"minimum_rate_observations": 0},
        {"minimum_rate_observations": 6},
    ],
)
def test_invalid_feature_config_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(FeatureValidationError):
        replace(DEFAULT_FEATURE_CONFIG, **overrides)  # type: ignore[arg-type]


def test_previous_season_scope_requires_explicit_identifier() -> None:
    with pytest.raises(FeatureValidationError, match="requires previous_season_id"):
        replace(
            DEFAULT_FEATURE_CONFIG,
            season_history_scope=SeasonHistoryScope.CURRENT_AND_PREVIOUS_SEASON,
        )


def test_previous_season_identifier_is_not_allowed_in_current_only_scope() -> None:
    with pytest.raises(FeatureValidationError, match="requires previous-season scope"):
        replace(DEFAULT_FEATURE_CONFIG, previous_season_id="s0")


def test_config_override_does_not_mutate_default() -> None:
    override = FeatureConfig(recent_window=3, extended_window=8)
    assert override.recent_window == 3
    assert DEFAULT_FEATURE_CONFIG.recent_window == 5
