from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from inspect import signature
from typing import Literal, cast

import pytest

from pitchvalue.features.config import FeatureConfig
from pitchvalue.features.contracts import (
    HistoricalMatch,
    MatchFeatures,
    MatchStatus,
    TargetFixture,
)
from pitchvalue.features.engine import compute_match_features
from pitchvalue.models.form.config import (
    FormModelConfig,
    MissingComponentPolicy,
    PartialCoveragePolicy,
)
from pitchvalue.models.form.contracts import (
    ComponentAnalysis,
    FormComponent,
    FormModelAnalysis,
    FormModelStatus,
    TeamFormSignal,
)
from pitchvalue.models.form.model import analyze_form_signal

D = Decimal
TARGET_TIME = datetime(2026, 8, 20, 18, tzinfo=UTC)
SMALL_WINDOWS = FeatureConfig(
    recent_window=2,
    extended_window=2,
    home_split_window=2,
    away_split_window=2,
)


def target() -> TargetFixture:
    return TargetFixture("target", "league", "s1", TARGET_TIME, "A", "B")


def match(
    match_id: str,
    days_before: int,
    home: str,
    away: str,
    home_score: int,
    away_score: int,
) -> HistoricalMatch:
    return HistoricalMatch(
        match_id,
        "league",
        "s1",
        TARGET_TIME - timedelta(days=days_before),
        home,
        away,
        MatchStatus.FINISHED,
        home_score,
        away_score,
    )


def neutral_features(*, partial: bool = False) -> MatchFeatures:
    history = [
        match("a-win", 10, "A", "X", 1, 0),
        match("a-loss", 5, "A", "Y", 0, 1),
        match("b-win", 10, "Z", "B", 0, 1),
        match("b-loss", 5, "W", "B", 1, 0),
    ]
    config = FeatureConfig() if partial else SMALL_WINDOWS
    return compute_match_features(target(), history, config)


def replace_form(
    features: MatchFeatures, side: str, group: str, **changes: object
) -> MatchFeatures:
    team = getattr(features, side)
    updated = replace(getattr(team, group), **changes)
    return replace(features, **{side: replace(team, **{group: updated})})


def component(
    result: FormModelAnalysis,
    side: Literal["home_team", "away_team"],
    name: FormComponent,
) -> ComponentAnalysis:
    team = cast(TeamFormSignal, getattr(result, side))
    return next(item for item in team.components if item.component is name)


def test_neutral_teams_have_equal_scores_and_zero_signal() -> None:
    result = analyze_form_signal(neutral_features())
    assert result.status is FormModelStatus.READY
    assert result.home_form_score == D("50.0")
    assert result.away_form_score == D("50.0")
    assert result.raw_form_difference == 0
    assert result.home_relative_form_signal == 0
    assert result.away_relative_form_signal == 0


def test_recent_and_extended_components_are_separate_and_auditable() -> None:
    result = analyze_form_signal(neutral_features())
    recent = component(result, "home_team", FormComponent.RECENT_FORM)
    extended = component(result, "home_team", FormComponent.EXTENDED_FORM)
    assert recent.score == extended.score == D("50.0")
    assert recent.inputs[0].name == "points_per_game"
    assert extended.component is FormComponent.EXTENDED_FORM


def test_stronger_home_recent_form_increases_home_score_and_signal() -> None:
    baseline = neutral_features()
    stronger = replace_form(
        baseline,
        "home_team",
        "recent",
        points_per_game=D("3"),
        goal_difference_per_game=D("2"),
    )
    before = analyze_form_signal(baseline)
    after = analyze_form_signal(stronger)
    assert after.home_form_score is not None and before.home_form_score is not None
    assert after.home_form_score > before.home_form_score
    assert after.home_relative_form_signal is not None and after.home_relative_form_signal > 0


def test_stronger_away_form_shifts_signal_toward_away() -> None:
    features = replace_form(
        neutral_features(),
        "away_team",
        "recent",
        points_per_game=D("3"),
        goal_difference_per_game=D("2"),
    )
    result = analyze_form_signal(features)
    assert result.home_relative_form_signal is not None and result.home_relative_form_signal < 0
    assert result.away_relative_form_signal is not None and result.away_relative_form_signal > 0


@pytest.mark.parametrize(("side", "expected_sign"), [("home_team", 1), ("away_team", -1)])
def test_stronger_venue_form_moves_signal_for_that_team(side: str, expected_sign: int) -> None:
    features = replace_form(
        neutral_features(),
        side,
        "venue_split",
        points_per_game=D("3"),
        goal_difference_per_game=D("2"),
    )
    result = analyze_form_signal(features)
    assert result.home_relative_form_signal is not None
    assert result.home_relative_form_signal * expected_sign > 0


def test_attack_component_is_league_relative_and_monotonic() -> None:
    baseline = neutral_features()
    stronger = replace_form(baseline, "home_team", "recent", goals_for_per_game=D("0.75"))
    stronger = replace_form(stronger, "home_team", "venue_split", goals_for_per_game=D("0.75"))
    before = analyze_form_signal(baseline).home_team.attack_score
    after_result = analyze_form_signal(stronger)
    assert before == D("50.0")
    assert (
        after_result.home_team.attack_score is not None
        and after_result.home_team.attack_score > before
    )
    attack = component(after_result, "home_team", FormComponent.ATTACK)
    assert attack.normalized_inputs[0].name == "recent_ratio"


def test_defense_component_direction_is_not_inverted() -> None:
    baseline = neutral_features()
    stronger = replace_form(baseline, "home_team", "recent", goals_against_per_game=D("0.25"))
    stronger = replace_form(stronger, "home_team", "venue_split", goals_against_per_game=D("0.25"))
    before = analyze_form_signal(baseline).home_team.defense_score
    after = analyze_form_signal(stronger).home_team.defense_score
    assert before == D("50.0")
    assert after is not None and after > before


def test_schedule_component_is_low_weight_and_cannot_dominate() -> None:
    features = neutral_features()
    home = features.home_team
    congested = replace(
        home.schedule,
        days_since_previous_match=D("2"),
        density=tuple(replace(item, match_count=20) for item in home.schedule.density),
    )
    changed = replace(features, home_team=replace(home, schedule=congested))
    result = analyze_form_signal(changed)
    assert result.home_team.schedule_score == D("20")
    assert result.home_form_score is not None and result.home_form_score >= D("48")


def test_complete_coverage_reports_ready() -> None:
    result = analyze_form_signal(neutral_features())
    assert result.status is FormModelStatus.READY
    assert result.home_team.coverage.complete_components == 6
    assert result.home_team.coverage.effective_weight_sum == D("1.00")


def test_partial_history_is_used_and_disclosed_by_default() -> None:
    result = analyze_form_signal(neutral_features(partial=True))
    assert result.status is FormModelStatus.READY
    assert result.home_team.coverage.partial_components >= 3
    assert result.diagnostics.partial_coverage_policy == "USE_PARTIAL"


def test_partial_history_can_be_excluded_by_config() -> None:
    config = FormModelConfig(partial_coverage_policy=PartialCoveragePolicy.EXCLUDE_PARTIAL)
    result = analyze_form_signal(neutral_features(partial=True), config)
    assert result.status is FormModelStatus.INPUT_INSUFFICIENT
    assert "HOME_OVERALL_FORM_REQUIRED" in result.reasons


def test_missing_schedule_is_excluded_and_available_weights_are_renormalized() -> None:
    features = neutral_features()
    no_schedule = replace(
        features.home_team.schedule, previous_match_kickoff=None, days_since_previous_match=None
    )
    features = replace(features, home_team=replace(features.home_team, schedule=no_schedule))
    result = analyze_form_signal(features)
    assert result.status is FormModelStatus.READY
    assert result.home_team.schedule_score is None
    assert result.home_team.coverage.effective_weight_sum == D("0.95")
    assert result.home_form_score == D("50.0")


def test_explicit_neutral_imputation_is_visible() -> None:
    features = neutral_features()
    no_schedule = replace(
        features.home_team.schedule, previous_match_kickoff=None, days_since_previous_match=None
    )
    features = replace(features, home_team=replace(features.home_team, schedule=no_schedule))
    config = FormModelConfig(missing_component_policy=MissingComponentPolicy.NEUTRAL_IMPUTE)
    result = analyze_form_signal(features, config)
    schedule_result = component(result, "home_team", FormComponent.SCHEDULE)
    assert schedule_result.score == D("50")
    assert schedule_result.reason == "NEUTRAL_IMPUTED"
    assert result.home_team.coverage.effective_weight_sum == D("1.00")


def test_missing_recent_can_use_extended_without_zero_fabrication() -> None:
    features = neutral_features()
    unavailable = compute_match_features(target(), []).home_team.recent
    changed = replace(features, home_team=replace(features.home_team, recent=unavailable))
    result = analyze_form_signal(changed)
    assert result.status is FormModelStatus.READY
    assert result.home_team.recent_form_score is None
    assert result.home_team.extended_form_score is not None


def test_unavailable_required_venue_returns_input_insufficient() -> None:
    features = neutral_features()
    unavailable = compute_match_features(target(), []).home_team.venue_split
    changed = replace(features, home_team=replace(features.home_team, venue_split=unavailable))
    result = analyze_form_signal(changed)
    assert result.status is FormModelStatus.INPUT_INSUFFICIENT
    assert result.home_form_score is None
    assert "HOME_VENUE_FORM_REQUIRED" in result.reasons


def test_no_history_is_input_insufficient_not_a_zero_score() -> None:
    result = analyze_form_signal(compute_match_features(target(), []))
    assert result.status is FormModelStatus.INPUT_INSUFFICIENT
    assert result.home_form_score is None
    assert result.raw_form_difference is None


def test_minimum_component_requirement_is_configurable() -> None:
    features = neutral_features()
    no_schedule = replace(
        features.home_team.schedule, previous_match_kickoff=None, days_since_previous_match=None
    )
    features = replace(features, home_team=replace(features.home_team, schedule=no_schedule))
    permissive = analyze_form_signal(features, FormModelConfig(minimum_scored_components=5))
    strict = analyze_form_signal(features, FormModelConfig(minimum_scored_components=6))
    assert permissive.status is FormModelStatus.READY
    assert strict.status is FormModelStatus.INPUT_INSUFFICIENT


def test_team_and_relative_scores_stay_in_contract_bounds() -> None:
    features = neutral_features()
    extreme = replace_form(
        features, "home_team", "recent", points_per_game=D("3"), goal_difference_per_game=D("99")
    )
    extreme = replace_form(
        extreme, "away_team", "recent", points_per_game=D("0"), goal_difference_per_game=D("-99")
    )
    result = analyze_form_signal(extreme)
    assert result.home_form_score is not None and D(0) <= result.home_form_score <= D(100)
    assert result.away_form_score is not None and D(0) <= result.away_form_score <= D(100)
    assert result.home_relative_form_signal is not None and D(
        -1
    ) <= result.home_relative_form_signal <= D(1)


def test_analysis_is_deterministic_and_serialization_is_stable() -> None:
    features = neutral_features()
    first = analyze_form_signal(features)
    second = analyze_form_signal(features)
    assert first == second
    assert first.to_dict() == second.to_dict()
    assert Decimal(first.to_dict()["home_form_score"]) == D("50")


def test_analysis_does_not_mutate_feature_input() -> None:
    features = neutral_features()
    before = features.to_dict()
    analyze_form_signal(features)
    assert features.to_dict() == before


def test_model_boundary_accepts_features_and_config_only() -> None:
    parameters = tuple(signature(analyze_form_signal).parameters)
    assert parameters == ("features", "config")
    target_fields = {item.name for item in fields(TargetFixture)}
    output_fields = {item.name for item in fields(FormModelAnalysis)}
    assert not {"home_score", "away_score", "result"} & target_fields
    assert not {"odds", "elo", "poisson", "publication_eligible"} & output_fields
